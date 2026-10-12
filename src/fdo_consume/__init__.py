"""fdo-consume: a PID and a consumer contract in, a binding and a record out."""
from . import contracts, loaders, pipeline, sources
from ._version import __version__
from .core import AccessError, AccessRecord, Limits
from .consume import CollectionConsumptionResult, ConsumptionResult, consume, consume_collection, consume_for_contracts

__all__ = [
    "consume", "consume_for_contracts", "consume_collection", "ConsumptionResult", "CollectionConsumptionResult",
    "AccessRecord", "AccessError", "Limits",
]

