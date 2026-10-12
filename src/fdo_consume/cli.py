"""Command line: fdo-consume consume|inspect <pid> [<pid> ...]."""
from __future__ import annotations

import argparse
import json

from .batch import access_collection, access_many
from .core import WANTS, exit_code
from .pipeline import DEPTHS
from .pipeline.access import access


def _common(cmd: argparse.ArgumentParser) -> None:
    cmd.add_argument("pids", nargs="+", metavar="pid")
    cmd.add_argument("--contract", default=None, help="a contract name, e.g. card")
    cmd.add_argument("--source", default="recorded", help="recorded (default) or live (HTTP/HTTPS PIDs)")
    cmd.add_argument("--profile-overlay", dest="overlay", default=None,
                     help="a map that adds terms to the profile (see profiles/maps)")
    cmd.add_argument("--profile", default=None, help="read the object by this map, whatever it declares")
    cmd.add_argument("--contracts", default=None, metavar="DIR", help="the consumer's own contract folder, searched first")
    cmd.add_argument("--profile-maps", default=None, metavar="DIR", help="extra profile maps (YAML)")
    cmd.add_argument("--recorded-dir", dest="fixtures", default=None, metavar="DIR",
                     help="folder of recorded objects")
    cmd.add_argument("--log-path", dest="log", default=None, metavar="FILE", help="append each record as a line")
    cmd.add_argument("--collection", action="store_true", help="the PID names a collection")


def build_parser() -> argparse.ArgumentParser:
    """consume: read for a contract and deliver a binding; inspect: run the pipeline to a chosen depth."""
    parser = argparse.ArgumentParser(prog="fdo-consume")
    commands = parser.add_subparsers(dest="command", required=True)
    _common(commands.add_parser("consume", help="read for a contract and deliver the binding"))
    cmd = commands.add_parser("inspect", help="run the pipeline to a chosen depth")
    _common(cmd)
    cmd.add_argument("--depth", default="match", help="one of: " + ", ".join(DEPTHS) + " (check is an alias of match)")
    cmd.add_argument("--want", default="reference", help="one of: " + ", ".join(WANTS))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command, print JSON, return the exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    depth, want = ("load", "binding") if args.command == "consume" else (args.depth, args.want)
    options = {
        "contract": args.contract,
        "depth": depth,
        "source": args.source,
        "want": want,
        "fixtures": args.fixtures,
        "overlay": args.overlay,
        "contracts": args.contracts,
        "profile_maps": args.profile_maps,
        "profile": args.profile,
        "log": args.log,
    }
    if args.collection and len(args.pids) != 1:
        parser.error("--collection takes exactly one PID")

    no_members = False
    if args.collection:
        result = access_collection(args.pids[0], **options)
        records = [result["collection"]] + result["records"]
        no_members = not result["records"]
    elif len(args.pids) == 1:
        result = access(args.pids[0], **options).to_dict()
        records = [result]
    else:
        result = access_many(args.pids, **options)
        records = result["records"]

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return exit_code(records, no_members)
