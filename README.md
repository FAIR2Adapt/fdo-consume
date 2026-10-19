# fdo-consume

`fdo-consume` is a consumer-side library developed in FAIR2Adapt for reading FAIR Digital Objects (FDOs): it resolves a PID, reads the object's RO-Crate and interprets it through a profile map (the CCA profile, the Knowledge Loom record profile, or plain RO-Crate).

Two ways to use it:

- **`describe(pid)`**: the object as its profile describes it (root fields, entities, declared resources, access), with resolution and validation statuses. Enough for a service that only needs to read an object, such as a question-answering or listing service.
- **`consume(pid, contract)`**: the same reading checked against a consumer contract, the consumer's own statement of what it needs. It returns a **binding** (plain JSON with the entities, resources and access the consumer asked for) and a **record** with separate resolution, validation, compatibility and delivery statuses and a diagnostic for every step that did not pass.

The package ships the profile maps of published profiles and the contract mechanism; it ships no consumer contract. Each consumer keeps its contracts, and any draft profile additions it relies on, in its own repository.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

Dependencies: PyYAML and PyLD (JSON-LD expansion; PyLD brings lxml, cachetools and frozendict). The RO-Crate contexts are bundled, so reading an object makes no network request unless `source="live"` is chosen.

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

Reading without a contract:

```python
from fdo_consume import describe

record = describe("https://example.org/stand-in/hamburg-loom-record", recorded_dir="fixtures/cca-demo")
record.descriptor    # root fields, entities, resources, as the profile map reads them
record.validation    # profile conformance, judged apart from any consumer
```

A recorded folder holds `pids.json` (`{"<pid>": {"fixture": "<name>"}}`) and `objects/<name>/ro-crate-metadata.json`; payload files stay next to the crate. A resource inside the crate has the URL `in-crate:<path>`: the path is relative to that folder, and the library reads no payload bytes. An object that declares no profile IRI (the current Knowledge Loom export) is read with `profile="knowledge-loom-0.1.0"`.

A contract names its consumer (`service`, `capability`), the needs (`term`, `level` must or should, an optional `reason`), the media types it `accepts`, and the overlay it needs (`profile_additions`); an optional `source` mapping may record where the needs come from. A term is a root field, an entity or a concept of a profile map (`fdo_consume.profiles.known_terms`); an overlay applies only to the map it extends, and the record's P2 step says when it was not applied.

## Command line

```bash
fdo-consume inspect <pid> --depth describe --recorded-dir fixtures/cca-demo
fdo-consume consume <pid> --contract cs3-map-v1 --contracts fixtures/contracts --profile-maps fixtures/maps --profile-overlay cca-dashboard-additions --recorded-dir fixtures/cca-dashboard
fdo-consume consume <pid> --contract cs3-evidence-v1 --contracts fixtures/contracts --recorded-dir fixtures/scenarios/loom-record --report html --out report.html
```

`--source recorded` (default) reads objects from a folder with a `pids.json`; `--source live` resolves HTTP(S) PIDs. The output is the JSON record (`--report json`), or an HTML or Markdown page rendered from it (`--report html`, `--report md`); `--out FILE` writes it to a file.

Exit codes: `0` ok, `1` not resolved, error, or a collection without members, `2` bad request, `3` one of the four statuses is FAIL.

**Note:** fdo-consume is developed for FAIR2Adapt and supports the FAIR2Adapt CCA Profile and the CCA dashboard-profile proposal developed by LifeWatch. As these profiles continue to evolve, this repository is under active development and will be updated accordingly.
