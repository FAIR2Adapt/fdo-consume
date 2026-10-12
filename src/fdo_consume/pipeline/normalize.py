"""Stage normalize: N1, the object's terms as expanded IRIs."""
from __future__ import annotations

from ..core import PASS, INDETERMINATE, Step, clip
from ..semantics import expand
from ..semantics.shape import hints
from .context import Context

SHOWN = 20


def normalize(ctx: Context) -> None:
    """N1: expand the crate's own @context; report what could not be expanded."""
    graph = expand(ctx.located.crate)
    ctx.canonical = graph
    ctx.record.semantics = {
        "available": graph.available,
        "contexts": graph.contexts,
        "unknown_contexts": graph.unknown_contexts[:SHOWN],
        "unknown_terms": graph.unknown_terms[:SHOWN],
        "unknown_terms_total": len(graph.unknown_terms),
        "problems": graph.problems[:SHOWN],
        "shape_hints": hints(graph),
    }
    if graph.available:
        detail = "; ".join(graph.contexts) or "inline context"
        if graph.unknown_contexts:
            detail += f"; {len(graph.unknown_contexts)} other context(s) not expanded"
        ctx.record.steps.append(Step("normalize", "N1", "context_usable", PASS, clip(detail)))
        return
    reason = "; ".join(item["detail"] for item in graph.problems) or "no usable @context"
    ctx.record.steps.append(Step("normalize", "N1", "context_usable", INDETERMINATE, clip(reason)))
