# fdo-consume

`fdo-consume` is a consumer-side library developed in FAIR2Adapt for reading FAIR Digital Objects (FDOs) and determining whether they can be used by a given application.

It reads the RO-Crate representation of an FDO, interprets it through a profile map, evaluates it against a consumer contract, and returns:

- a **binding**: plain JSON containing the entities, resources, and access information required by the application;
- a **record**: separate resolution, validation, compatibility, and delivery statuses, together with diagnostics for non-passing steps.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .

## Usage

```python
from fdo_consume import consume

result = consume(
    "https://example.org/object/full",
    "map-panel-v1",
    recorded_dir="fixtures/example-profile",
    profile_maps="fixtures/example-profile/maps",      # external profile map; no code change required
    contracts="fixtures/example-profile/contracts",    # consumer-owned contracts
)

result.is_usable     # True if the contract is met and a binding is delivered
result.binding       # application-facing binding, or None
result.statuses      # resolution, validation, compatibility, and delivery
result.diagnostics   # diagnostics for FAIL, PARTIAL, or INDETERMINATE steps
result.record        # complete AccessRecord
result.summary()     # plain dict suitable for logging or UI presentation
```

Several contracts can be evaluated against the same object, and collections can be consumed in the same way:

**Note:** fdo-consume is developed for FAIR2Adapt and supports the FAIR2Adapt CCA Profile and the CCA dashboard-profile proposal developed by LifeWatch. As these profiles continue to evolve, this repository is under active development and will be updated accordingly.

