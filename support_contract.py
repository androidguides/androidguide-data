"""Validation helpers for AndroidGuides support-window metadata.

The guarded pipeline and consumers share this contract so precision and meaning
cannot drift independently.
"""

from datetime import date
import re


PRECISIONS = {"day", "month", "unknown"}
BASES = {
    "manufacturer_published",
    "policy_calculation",
    "aggregator",
}
MEANINGS = {
    "minimum_guarantee",
    "scheduled_endpoint",
    "up_to",
    "estimate",
}
ALLOWED_MEANINGS_BY_BASIS = {
    "manufacturer_published": {
        "minimum_guarantee",
        "scheduled_endpoint",
        "up_to",
    },
    "policy_calculation": {"minimum_guarantee", "up_to", "estimate"},
    "aggregator": {"estimate"},
}
OBSERVATION_STATUSES = {
    "listed_under_current_policy",
    "no_longer_receives_updates",
    "removed_from_support_scope",
    "unknown",
}
REQUIRED_OBSERVATION_FIELDS = {"status", "observed_on", "provenance"}
REQUIRED_WINDOW_FIELDS = {
    "published_value",
    "precision",
    "basis",
    "meaning",
    "raw_upstream_value",
    "provenance",
}
REQUIRED_PROVENANCE_FIELDS = {
    "source_url",
    "checked_on",
    "market",
    "model_codes",
    "note",
}
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _iso_date(value, field, failures):
    if not isinstance(value, str):
        failures.append(f"{field} must be an ISO date string")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        failures.append(f"{field} must be an ISO date string")
        return None


def _validate_provenance(provenance, field, failures):
    if not isinstance(provenance, dict):
        failures.append(f"{field} must be an object")
        return

    missing = sorted(REQUIRED_PROVENANCE_FIELDS - set(provenance))
    if missing:
        failures.append(f"{field} missing fields: " + ", ".join(missing))
        return

    source_url = provenance["source_url"]
    if not isinstance(source_url, str) or not source_url.startswith("https://"):
        failures.append(f"{field}.source_url must be HTTPS")
    _iso_date(provenance["checked_on"], f"{field}.checked_on", failures)
    if not isinstance(provenance["market"], str) or not provenance["market"].strip():
        failures.append(f"{field}.market must be a non-empty string")
    model_codes = provenance["model_codes"]
    if not isinstance(model_codes, list) or any(
        not isinstance(code, str) or not code.strip() for code in model_codes
    ):
        failures.append(f"{field}.model_codes must be a list of non-empty strings")
    if not isinstance(provenance["note"], str) or not provenance["note"].strip():
        failures.append(f"{field}.note must be a non-empty string")
    if "list_qualifier" in provenance and (
        not isinstance(provenance["list_qualifier"], str)
        or not provenance["list_qualifier"].strip()
    ):
        failures.append(f"{field}.list_qualifier must be a non-empty string")


def validate_support_window(record: dict) -> list[str]:
    """Return contract failures for one generated device record."""
    failures = []
    window = record.get("support_window")
    if not isinstance(window, dict):
        return ["support_window must be an object"]

    missing = sorted(REQUIRED_WINDOW_FIELDS - set(window))
    if missing:
        failures.append(f"support_window missing fields: {', '.join(missing)}")
        return failures

    precision = window["precision"]
    basis = window["basis"]
    meaning = window["meaning"]
    if precision not in PRECISIONS:
        failures.append(f"precision must be one of {sorted(PRECISIONS)}")
    if basis not in BASES:
        failures.append(f"basis must be one of {sorted(BASES)}")
    if meaning not in MEANINGS:
        failures.append(f"meaning must be one of {sorted(MEANINGS)}")
    if basis in ALLOWED_MEANINGS_BY_BASIS and meaning not in ALLOWED_MEANINGS_BY_BASIS[basis]:
        failures.append(f"meaning {meaning!r} is incompatible with basis {basis!r}")

    published = window["published_value"]
    if precision == "day":
        _iso_date(published, "published_value", failures)
    elif precision == "month":
        if not isinstance(published, str) or not MONTH_RE.fullmatch(published):
            failures.append("month precision requires published_value in YYYY-MM form")
    elif precision == "unknown":
        if published is not None:
            failures.append("unknown precision requires null published_value")

    _validate_provenance(window["provenance"], "provenance", failures)

    observation = record.get("support_observation")
    if observation is not None:
        if not isinstance(observation, dict):
            failures.append("support_observation must be an object")
        else:
            missing_observation = sorted(REQUIRED_OBSERVATION_FIELDS - set(observation))
            if missing_observation:
                failures.append(
                    "support_observation missing fields: "
                    + ", ".join(missing_observation)
                )
            else:
                status = observation["status"]
                if status not in OBSERVATION_STATUSES:
                    failures.append(
                        "support_observation.status must be one of "
                        + str(sorted(OBSERVATION_STATUSES))
                    )
                _iso_date(
                    observation["observed_on"],
                    "support_observation.observed_on",
                    failures,
                )
                _validate_provenance(
                    observation["provenance"],
                    "support_observation.provenance",
                    failures,
                )

    source = record.get("source")
    if source not in {"endoflife.date", "override"}:
        failures.append("source must remain 'endoflife.date' or 'override'")

    legacy_eol = _iso_date(record.get("eol"), "eol", failures)
    if legacy_eol and precision == "day":
        try:
            if legacy_eol != date.fromisoformat(published):
                failures.append("day precision requires legacy eol to match published_value")
        except (TypeError, ValueError):
            pass
    if legacy_eol and precision == "month" and isinstance(published, str) and MONTH_RE.fullmatch(published):
        if legacy_eol.strftime("%Y-%m") != published:
            failures.append("month precision requires legacy eol to fall within published month")

    return failures


def exact_end_date(record: dict):
    """Return an exact supported-through date only when the source has day precision."""
    window = record.get("support_window", {})
    if window.get("precision") != "day":
        return None
    try:
        return date.fromisoformat(window["published_value"])
    except (KeyError, TypeError, ValueError):
        return None
