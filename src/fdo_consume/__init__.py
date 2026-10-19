"""fdo-consume: reads a FAIR Digital Object for a consumer contract and returns a binding and an access record."""
from . import contracts, loaders, pipeline, sources
from ._version import __version__
from .core import AccessError, AccessRecord, Limits
from .consume import CollectionConsumptionResult, ConsumptionResult, consume, consume_collection, consume_for_contracts, describe

__all__ = [
    "consume", "consume_for_contracts", "consume_collection", "describe", "ConsumptionResult", "CollectionConsumptionResult",
    "AccessRecord", "AccessError", "Limits",
]
