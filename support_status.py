"""Shared support-state and display rules for generated consumers."""

from datetime import date, datetime


STATES = {"supported", "ending", "guarantee_elapsed", "ended", "unknown"}
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _day(value: str) -> date:
    return datetime.fromisoformat(value).date()


def _month(value: str) -> tuple[int, int]:
    year, month = value.split("-")
    return int(year), int(month)


def month_distance(start: date, target: tuple[int, int]) -> int:
    """Return whole calendar months from start's month to target."""
    return (target[0] - start.year) * 12 + target[1] - start.month


def support_state(record: dict, as_of: date) -> str:
    """Classify support without inventing precision or an observed stop."""
    observation = record.get("support_observation") or {}
    listed_current = observation.get("status") == "listed_under_current_policy"
    if observation.get("status") in {
        "no_longer_receives_updates",
        "removed_from_support_scope",
    }:
        return "ended"

    window = record.get("support_window") or {}
    if window.get("meaning") == "up_to":
        if window.get("precision") == "month":
            target = _month(window["published_value"])
            return (
                "supported"
                if listed_current and month_distance(as_of, target) >= 0
                else "unknown"
            )
        return "supported" if listed_current else "unknown"
    if window.get("precision") == "month":
        target = _month(window["published_value"])
        distance = month_distance(as_of, target)
        if distance < 0:
            return "guarantee_elapsed"
        if distance <= 12:
            return "ending"
        return "supported"

    if window.get("precision") == "unknown":
        return "supported" if listed_current else "unknown"

    eol = _day(record["eol"])
    days = (eol - as_of).days
    if days < 0:
        return "ended"
    if days <= 365:
        return "ending"
    return "supported"


def support_date_text(record: dict) -> str:
    """Return a truthful human date label for the evidence precision."""
    window = record.get("support_window") or {}
    if window.get("precision") == "month":
        year, month = _month(window["published_value"])
        return f"{MONTHS[month - 1]} {year} — exact end date not specified"
    if window.get("precision") == "unknown":
        return "Exact end date not established"
    value = window.get("published_value") or record["eol"]
    parsed = _day(value)
    return f"{MONTHS[parsed.month - 1]} {parsed.day}, {parsed.year}"


def support_sentence(record: dict, as_of: date) -> str:
    """Return the status clause used by plain-HTML consumers."""
    state = support_state(record, as_of)
    name = f"{record['brand']} {record['model']}"
    window = record.get("support_window") or {}
    precision = window.get("precision")
    observation = record.get("support_observation") or {}
    observed_ended = observation.get("status") in {
        "no_longer_receives_updates",
        "removed_from_support_scope",
    }

    if state == "ended" and observed_ended:
        if precision == "month":
            return (
                f"Current manufacturer evidence shows that the {name} no longer "
                f"receives security updates; its stated minimum guarantee was through "
                f"{support_date_text(record)}, and the exact stop day is not established here."
            )
        if precision == "unknown":
            return (
                f"Current manufacturer evidence shows that the {name} no longer "
                "receives security updates; its exact historical cutoff date is not "
                "established here."
            )
        return (
            f"Current manufacturer evidence shows that the {name} no longer receives "
            f"security updates; its published support date is {support_date_text(record)}, "
            "but the observation does not establish the exact stop day."
        )

    if precision == "month":
        label = support_date_text(record)
        if window.get("meaning") == "up_to":
            month_label = label.split(" —", 1)[0]
            if state == "supported":
                return (
                    f"Current manufacturer evidence lists the {name} for security "
                    f"updates. The published support duration may run up to {month_label}; "
                    "an exact endpoint is not published."
                )
            return (
                f"The manufacturer describes security support for the {name} as "
                f"running up to {month_label}; current support status is not established "
                "here."
            )
        if state == "guarantee_elapsed":
            return f"The stated security-update guarantee period for the {name} has elapsed ({label})."
        if month_distance(as_of, _month(window["published_value"])) == 0:
            return f"The guaranteed security-update window for the {name} ends this month ({label})."
        return f"The guaranteed security-update window for the {name} ends in {label}."

    if precision == "unknown":
        if observation.get("status") == "listed_under_current_policy":
            return (
                f"Current manufacturer evidence lists the {name} for security updates; "
                "its exact support-end date is not published."
            )
        return f"The current security-update status of the {name} is not established here; its exact support-end date is also unknown."

    label = support_date_text(record)
    if state == "ended":
        return f"Android security updates for the {name} ended on {label}."
    return f"Android security updates for the {name} are scheduled to end on {label}."
