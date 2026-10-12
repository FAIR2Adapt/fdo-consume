"""Resolve live HTTP PIDs to JSON crates with bounded network requests."""
from __future__ import annotations

import math
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..core import AccessError, Limits, Located, parse_crate, refuse_large_crate, sha256_bytes
from ..pipeline.fallback_reader import _is_private_address
from ..registry import register


class _Redirects(HTTPRedirectHandler):
    def __init__(self, chain: list[str], maximum: int, allow_private: bool = False):
        self.chain = chain
        self.maximum = maximum
        self.allow_private = allow_private

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if len(self.chain) - 1 >= self.maximum or newurl in self.chain:
            raise AccessError("transport.http_error", "redirect limit exceeded or redirect loop")
        _http_url(newurl, self.allow_private)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            self.chain.append(newurl)
        return redirected


def _http_url(url: str, allow_private: bool = False) -> None:
    try:
        parsed = urlsplit(url)
        valid = parsed.scheme in ("http", "https") and bool(parsed.hostname)
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise AccessError("request.bad_pid", "the live source needs an HTTP or HTTPS PID")
    if not allow_private and _private_host(parsed.hostname):
        raise AccessError("request.bad_pid", "the live source refuses private, loopback and link-local hosts")


def _private_host(host: str) -> bool:
    """True when the host name or any address it resolves to is private, loopback or link-local (SSRF guard)."""
    if _is_private_address(host):
        return True
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except (OSError, UnicodeError):
        return False   # unresolvable: the request itself fails later
    return any(_is_private_address(address) for address in addresses)


@register("locator", "live")
def locate_live(pid: str, options: dict, limits: Limits) -> Located:
    """Fetch a JSON crate; timeout, max_redirects and allow_private_hosts (trusted use only) are configurable."""
    allow_private = options.get("allow_private_hosts") is True
    _http_url(pid, allow_private)
    timeout = options.get("timeout", 10.0)
    redirects = options.get("max_redirects", 10)
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        raise AccessError("request.bad_option", "timeout must be a positive finite number")
    if isinstance(redirects, bool) or not isinstance(redirects, int) or redirects < 0:
        raise AccessError("request.bad_option", "max_redirects must be a non-negative integer")

    chain = [pid]
    opener = build_opener(_Redirects(chain, redirects, allow_private))
    request = Request(pid, headers={"Accept": "application/ld+json, application/json",
                                    "Accept-Encoding": "identity"})
    try:
        with opener.open(request, timeout=timeout) as response:
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    size = int(length)
                except ValueError:
                    size = 0
                refuse_large_crate(size, limits)
            data = response.read(limits.max_crate_bytes + 1)
            refuse_large_crate(len(data), limits)
    except HTTPError as error:
        error.close()
        code = "resolution.gone" if error.code in (404, 410) else "transport.http_error"
        raise AccessError(code, f"HTTP {error.code} resolving the PID") from None
    except TimeoutError:
        raise AccessError("transport.timeout", "no answer within the live source timeout") from None
    except URLError as error:
        code = "transport.timeout" if isinstance(error.reason, TimeoutError) else "transport.connection"
        raise AccessError(code, str(error.reason)) from None
    except OSError as error:
        raise AccessError("transport.connection", str(error)) from None

    return Located(pid, parse_crate(data), chain, sha256_bytes(data), len(data))
