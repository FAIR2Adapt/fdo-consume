"""HTML and Markdown rendering of a JSON result; the JSON record remains the normative output."""
from __future__ import annotations

import html
import json
from dataclasses import dataclass, field

from .core import DIMENSIONS

FORMATS = ("json", "html", "md")
STYLE = ("body{font:15px/1.45 system-ui,sans-serif;margin:2rem auto;max-width:72rem;padding:0 1rem;color:#222}"
         "table{border-collapse:collapse;margin:.5rem 0 1.25rem}th,td{border:1px solid #ccc;padding:.25rem .6rem;"
         "text-align:left;vertical-align:top}th{background:#f3f3f3}h2{margin-top:2rem}dl{display:grid;"
         "grid-template-columns:max-content 1fr;gap:.2rem 1rem}dt{font-weight:600}dd{margin:0;word-break:break-all}"
         ".PASS{color:#1a7f37}.PARTIAL{color:#9a6700}.FAIL{color:#b91c1c}.INDETERMINATE,.NOT_ATTEMPTED{color:#666}")


@dataclass
class Block:
    """One section of a report: a heading, some facts, and at most one table."""

    title: str
    facts: list[tuple[str, str]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


def render(result: dict, fmt: str) -> str:
    """The result of a CLI call (one record, a batch, or a collection) in the chosen format."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown report format: {fmt!r}; one of {FORMATS}")
    if fmt == "json":
        return json.dumps(result, indent=2, ensure_ascii=False)
    blocks = _blocks(result)
    return _html(blocks) if fmt == "html" else _markdown(blocks)


def _blocks(result: dict) -> list[Block]:
    records = result["records"] if "records" in result else [result]
    blocks = []
    if "collection" in result:
        blocks.extend(_record_blocks(result["collection"], "Collection"))
    if "summary" in result:
        blocks.append(_summary_block(result["summary"]))
    for index, record in enumerate(records, 1):
        blocks.extend(_record_blocks(record, f"Object {index}" if len(records) > 1 else "Object"))
    return blocks


def _summary_block(summary: dict) -> Block:
    block = Block("Summary", [("objects", str(summary.get("total", "")))])
    for outcome, count in sorted(summary.get("by_outcome", {}).items()):
        block.facts.append((f"outcome {outcome}", str(count)))
    block.columns = ["dimension", *sorted({s for d in summary.get("by_dimension", {}).values() for s in d})]
    for name, counts in summary.get("by_dimension", {}).items():
        block.rows.append([name, *[str(counts.get(status, 0)) for status in block.columns[1:]]])
    return block


def _record_blocks(record: dict, title: str) -> list[Block]:
    request = record.get("request", {})
    head = Block(f"{title}: {request.get('pid', '')}")
    head.facts = [("contract", str(record.get("contract_id") or request.get("contract") or "none")),
                  ("outcome", str(record.get("outcome"))), ("reached", str(record.get("reached"))),
                  ("source", str(request.get("source", "")))]
    if record.get("stopped"):
        head.facts.append(("stopped", str(record["stopped"])))
    if record.get("error"):
        head.facts.append(("error", f"{record['error'].get('code')}: {record['error'].get('message')}"))
    for name in DIMENSIONS:
        head.facts.append((name, str(record.get(name, {}).get("status", "NOT_ATTEMPTED"))))
    head.facts.append(("package", str(record.get("package_version", ""))))
    blocks = [head]
    steps = record.get("steps", [])
    if steps:
        block = Block("Steps", columns=["stage", "step", "status", "detail"])
        block.rows = [[s["stage"], f"{s['id']} {s['name']}", s["status"], s.get("detail", "")] for s in steps]
        blocks.append(block)
    semantics = record.get("semantics") or {}
    if semantics.get("unknown_terms") or semantics.get("unknown_contexts") or semantics.get("problems"):
        block = Block("Terms the reader could not expand")
        block.facts = [("contexts", ", ".join(semantics.get("contexts", [])) or "none"),
                       ("unknown contexts", ", ".join(semantics.get("unknown_contexts", [])) or "none"),
                       ("unknown terms", ", ".join(semantics.get("unknown_terms", [])) or "none"),
                       ("problems", "; ".join(f"{p.get('code')}: {p.get('detail')}" for p in semantics.get("problems", [])) or "none")]
        blocks.append(block)
    binding = (record.get("loaded") or {}).get("value")
    if isinstance(binding, dict) and binding.get("schema", "").startswith("fdo-consume-binding"):
        blocks.extend(_binding_blocks(binding))
    return blocks


def _binding_blocks(binding: dict) -> list[Block]:
    obj = binding.get("object", {})
    block = Block("Binding", [("name", str(obj.get("name") or "")), ("profiles", ", ".join(obj.get("profiles") or []) or "none"),
                              ("map", str(obj.get("map") or "none")), ("overlay", str(obj.get("overlay") or "none")),
                              ("access", str((obj.get("access") or {}).get("state", "unknown"))),
                              ("selected", ", ".join(binding.get("selected") or []) or "none")])
    counts: dict[str, int] = {}
    for entity in binding.get("entities", []):
        counts[entity.get("type", "?")] = counts.get(entity.get("type", "?"), 0) + 1
    block.facts.append(("entities", ", ".join(f"{n} {t}" for t, n in sorted(counts.items())) or "none"))
    blocks = [block]
    resources = binding.get("resources", [])
    if resources:
        table = Block("Resources", columns=["id", "media type", "access", "payload", "accepted"])
        table.rows = [[r.get("id", ""), r.get("media_type") or "", (r.get("access") or {}).get("state", "unknown"),
                       "yes" if r.get("payload") else (r.get("why_not_payload") or "no"), "yes" if r.get("accepted") else "no"]
                      for r in resources]
        blocks.append(table)
    related = binding.get("related", [])
    if related:
        table = Block("Related objects", columns=["id", "name", "profiles", "has map"])
        table.rows = [[r.get("id", ""), r.get("name") or "", ", ".join(r.get("profiles") or []), "yes" if r.get("has_map") else "no"]
                      for r in related]
        blocks.append(table)
    return blocks


def _html(blocks: list[Block]) -> str:
    out = ["<!doctype html>", "<html lang=\"en\"><head><meta charset=\"utf-8\">", f"<title>fdo-consume report</title><style>{STYLE}</style>",
           "</head><body>", "<h1>fdo-consume report</h1>"]
    for block in blocks:
        out.append(f"<h2>{html.escape(block.title)}</h2>")
        if block.facts:
            out.append("<dl>" + "".join(f"<dt>{html.escape(k)}</dt><dd{_status_class(v)}>{html.escape(v)}</dd>" for k, v in block.facts) + "</dl>")
        if block.rows:
            out.append("<table><thead><tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in block.columns) + "</tr></thead><tbody>")
            for row in block.rows:
                out.append("<tr>" + "".join(f"<td{_status_class(cell)}>{html.escape(cell)}</td>" for cell in row) + "</tr>")
            out.append("</tbody></table>")
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def _status_class(value: str) -> str:
    return f' class="{value}"' if value in ("PASS", "PARTIAL", "FAIL", "INDETERMINATE", "NOT_ATTEMPTED") else ""


def _markdown(blocks: list[Block]) -> str:
    out = ["# fdo-consume report", ""]
    for block in blocks:
        out.extend([f"## {_cell(block.title)}", ""])
        for key, value in block.facts:
            out.append(f"- {_cell(key)}: {_cell(value)}")
        if block.facts:
            out.append("")
        if block.rows:
            out.append("| " + " | ".join(block.columns) + " |")
            out.append("|" + "---|" * len(block.columns))
            for row in block.rows:
                out.append("| " + " | ".join(_cell(cell) for cell in row) + " |")
            out.append("")
    return "\n".join(out)


def _cell(value: object) -> str:
    """Text inside Markdown: one line, no pipes, no raw HTML."""
    text = "" if value is None else str(value)
    return " ".join(text.split()).replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
