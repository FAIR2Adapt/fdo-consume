"""Test helper: the worst status over steps and dimensions (the record itself has no overall status)."""
DIMENSIONS = ("resolution", "validation", "compatibility", "delivery")


def worst_status(record) -> str:
    data = record if isinstance(record, dict) else record.to_dict()
    statuses = [s["status"] for s in data["steps"]]
    statuses += [data[n]["status"] for n in DIMENSIONS if data[n]["status"] != "NOT_ATTEMPTED"]
    if "FAIL" in statuses:
        return "FAIL"
    if "INDETERMINATE" in statuses or data["outcome"] != "ok":
        return "INDETERMINATE"
    if "PARTIAL" in statuses:
        return "PARTIAL"
    return "PASS"
