"""The pipeline: one object through the stages."""
from . import check_contract, fallback_reader  # noqa: F401  (registers the fallback describer and the contract check)
from .context import Context
from .interpret import describe, normal_pid
from .load import load
from .locate import locate
from .match import match
from .normalize import normalize
from .select import select

STAGES = (
    ("locate", locate),
    ("normalize", normalize),
    ("describe", describe),
    ("match", match),
    ("select", select),
    ("load", load),
)
DEPTHS = tuple(name for name, _ in STAGES)
ALIASES = {"check": "match"}
