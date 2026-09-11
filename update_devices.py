#!/usr/bin/env python3
"""
AndroidGuides.com — Device EOL database updater (Pipe #1, GUARDED — P1)

Pulls device support data from the endoflife.date API, applies manual
corrections from overrides.json, VALIDATES the result, and only then
regenerates devices.json. If any validation gate fails, nothing is
written, the process exits non-zero, GitHub Actions marks the run
failed, and GitHub emails the owner. The previous devices.json stays
live — bad data can never reach visitors.

Usage:
    python update_devices.py            # fetch live, validate, write devices.json
    python update_devices.py --dry-run  # fetch live, validate, print report, write nothing
"""

import json
import re
import sys
import urllib.request
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path

from support_contract import validate_support_window
from support_status import support_state

API_BASE = "https://endoflife.date/api"
SOURCES = {
    "Google": "pixel.json",
    "Samsung": "samsung-mobile.json",
}
OUTPUT = Path(__file__).parent / "devices.json"
OVERRIDES_FILE = Path(__file__).parent / "overrides.json"
PIXEL_AUDIT_FILE = Path(__file__).parent / "pixel-support-audit.json"
USER_AGENT = "AndroidGuideBot/1.0 (androidguides.com; contact: contact@androidguides.com)"

# ---------------------------------------------------------------- filters
# Only keep US-relevant Samsung lines; Pixel keeps everything phone-shaped.
SAMSUNG_KEEP = re.compile(
    r"^Galaxy (S\d{2}|Z (Fold|Flip)|A\d{2}\b)", re.IGNORECASE
)
PIXEL_SKIP = re.compile(r"(Tablet|Watch|Buds)", re.IGNORECASE)

# ---------------------------------------------------------------- validation config
REQUIRED_FIELDS = ("id", "brand", "model", "released", "eol", "source")
MIN_DEVICES = 100          # absolute floor — below this something is badly wrong
MAX_DEVICES = 500          # absolute ceiling — above this the filters broke
COUNT_TRIPWIRE = 0.10      # fail if count moves more than ±10% vs current devices.json
MIN_PER_BRAND = {"Google": 15, "Samsung": 40}

# Canary anchor devices: stable, long-lived records that must ALWAYS exist
# with exactly these release dates. If one vanishes or its release date
# shifts, the upstream source has changed shape — halt and investigate.
# (eol is deliberately NOT pinned: EOL dates may legitimately change.)
CANARIES = {
    "google-pixel-8": "2023-10-04",
    "google-pixel-6": "2021-10-28",
    "samsung-galaxy-s24": "2024-01-24",
    "samsung-galaxy-z-fold5": "2023-08-11",
}


def fetch(endpoint: str) -> list:
    """Fetch one product list from the endoflife.date API."""
    url = f"{API_BASE}/{endpoint}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def slugify(brand: str, model: str) -> str:
    s = f"{brand}-{model}".lower()
    s = re.sub(r"[+]", "-plus", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def normalize(brand: str, raw: list, semantic_failures=None) -> list:
    """Convert endoflife.date records to our schema. Facts only."""
    out = []
    for item in raw:
        model = item.get("releaseLabel") or item.get("cycle", "")
        if brand == "Samsung" and not SAMSUNG_KEEP.match(model):
            continue
        if brand == "Google" and PIXEL_SKIP.search(model):
            continue
        if brand == "Google" and not model.startswith("Pixel"):
            model = f"Pixel {model}"
        eol = item.get("eol")
        released = item.get("releaseDate")
        if model and not isinstance(eol, str) and isinstance(item.get("support"), str):
            device_id = slugify(brand, model)
            message = (
                f"{brand} {model}: explicit security EOL missing; "
                "support date cannot substitute")
            print(
                f"[WARN] {message}")
            if semantic_failures is not None:
                semantic_failures.append({"id": device_id, "message": message})
        if not (model and released and isinstance(eol, str)):
            continue  # skip records without hard dates
        out.append({
            "id": slugify(brand, model),
            "brand": brand,
            "model": model,
            "released": released,
            "eol": eol,
            "source": "endoflife.date",
        })
    return out


def load_existing() -> dict:
    if OUTPUT.exists():
        return {d["id"]: d for d in json.loads(OUTPUT.read_text(encoding="utf-8"))["devices"]}
    return {}


def apply_pixel_support_metadata(devices: list, semantic_failures=None, audit=None) -> list:
    """Attach reviewed Pixel precision metadata and reject unaudited drift."""
    if audit is None:
        audit = json.loads(PIXEL_AUDIT_FILE.read_text(encoding="utf-8"))
    if semantic_failures is None:
        semantic_failures = []

    by_id = {d["id"]: d for d in devices}
    audit_by_id = {item["id"]: item for item in audit.get("records", [])}
    pixel_ids = {d["id"] for d in devices if d.get("brand") == "Google"}
    audit_ids = set(audit_by_id)
    for missing in sorted(pixel_ids - audit_ids):
        semantic_failures.append({
            "id": missing,
            "message": "Google Pixel record has no reviewed support-date audit entry",
        })
    for stale in sorted(audit_ids - pixel_ids):
        semantic_failures.append({
            "id": stale,
            "message": "reviewed Pixel audit entry is missing from the generated dataset",
        })

    policy_url = audit["sources"]["current_policy"]
    availability_url = audit["sources"]["us_availability"]
    upstream_url = audit["sources"]["upstream_feed"]
    for device_id in sorted(pixel_ids & audit_ids):
        device = by_id[device_id]
        item = audit_by_id[device_id]
        drift = [
            field for field, audit_field in (
                ("model", "model"),
                ("released", "released"),
                ("eol", "legacy_eol"),
            )
            if device.get(field) != item.get(audit_field)
        ]
        if drift:
            semantic_failures.append({
                "id": device_id,
                "message": "Pixel source changed audited field(s): " + ", ".join(drift),
            })
            continue

        if item["group"] == "current_policy":
            device["support_window"] = {
                "published_value": item["published_value"],
                "precision": "month",
                "basis": "policy_calculation",
                "meaning": "minimum_guarantee",
                "raw_upstream_value": item["legacy_eol"],
                "provenance": {
                    "source_url": policy_url,
                    "checked_on": audit["audited_on"],
                    "market": "US",
                    "model_codes": [],
                    "note": (
                        "Calculated from Google's update-policy duration and the "
                        f"Google Store US availability month {item['availability_month']} "
                        f"published at {availability_url}; no exact final patch day is published."
                    ),
                },
            }
            observation_status = "listed_under_current_policy"
            observation_note = "Google currently lists this model under its update policy."
        else:
            device["support_window"] = {
                "published_value": None,
                "precision": "unknown",
                "basis": "aggregator",
                "meaning": "estimate",
                "raw_upstream_value": item["legacy_eol"],
                "provenance": {
                    "source_url": upstream_url,
                    "checked_on": audit["audited_on"],
                    "market": "US",
                    "model_codes": [],
                    "note": (
                        "The raw exact-looking date is retained for compatibility but is "
                        "not attributed to Google; current Google evidence does not establish "
                        "the historical cutoff day."
                    ),
                },
            }
            observation_status = "no_longer_receives_updates"
            observation_note = (
                "Google currently lists this model as no longer receiving Android version "
                "or security updates; this observation does not establish the historical stop date."
            )
        device["support_observation"] = {
            "status": observation_status,
            "observed_on": audit["audited_on"],
            "provenance": {
                "source_url": policy_url,
                "checked_on": audit["audited_on"],
                "market": "US",
                "model_codes": [],
                "note": observation_note,
            },
        }
    return devices


# ---------------------------------------------------------------- overrides (P1)
def apply_overrides(devices: list, semantic_failures=None, entries=None) -> list:
    """Merge manual corrections from overrides.json. Runs LAST so a human
    fact always beats the automated source. A provenance failure is cleared
    only by a sourced date or an explicit exclusion for the same device id.
    See PIPELINE-OPS.md for format."""
    if entries is None:
        if not OVERRIDES_FILE.exists():
            return devices
        data = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
        entries = data.get("overrides", [])
    if not entries:
        return devices
    by_id = {d["id"]: d for d in devices}
    applied = 0
    unresolved_ids = {
        failure["id"] for failure in (semantic_failures or [])
    }
    cleared_ids = set()
    for ov in entries:
        oid = ov.get("id")
        if not oid or not ov.get("reason"):
            print(f"[WARN] override skipped (needs 'id' and 'reason'): {ov}")
            continue
        if ov.get("remove") is True:
            removed = by_id.pop(oid, None) is not None
            if removed:
                print(f"  * OVERRIDE remove: {oid} ({ov['reason']})")
                applied += 1
            elif oid in unresolved_ids:
                print(f"  * OVERRIDE exclude unresolved: {oid} ({ov['reason']})")
                applied += 1
            else:
                print(f"[WARN] override remove: id not found: {oid}")
            if removed or oid in unresolved_ids:
                cleared_ids.add(oid)
            continue
        fields = ov.get("fields", {})
        bad_keys = set(fields) - set(REQUIRED_FIELDS)
        if bad_keys:
            print(f"[WARN] override {oid}: unknown fields {bad_keys} ignored")
            fields = {k: v for k, v in fields.items() if k not in bad_keys}
        if oid in by_id:
            by_id[oid].update(fields)
            by_id[oid]["source"] = "override"
            print(f"  * OVERRIDE patch: {oid} {fields} ({ov['reason']})")
            applied += 1
        elif ov.get("add") is True:
            record = {"id": oid, "source": "override", **fields}
            missing = [f for f in REQUIRED_FIELDS if not record.get(f)]
            if missing:
                print(f"[WARN] override add {oid}: missing {missing} — skipped")
                continue
            by_id[oid] = record
            print(f"  * OVERRIDE add: {oid} ({ov['reason']})")
            applied += 1
        else:
            print(f"[WARN] override {oid}: id not in dataset (add:true to insert)")
            continue

        basis = ov.get("security_eol_basis")
        eol_value = fields.get("eol")
        if basis in {"manufacturer_exact", "manufacturer_month_end"} and eol_value:
            precision = "day" if basis == "manufacturer_exact" else "month"
            published_value = eol_value if precision == "day" else eol_value[:7]
            by_id[oid]["support_window"] = {
                "published_value": published_value,
                "precision": precision,
                "basis": "manufacturer_published",
                "meaning": "scheduled_endpoint",
                "raw_upstream_value": ov.get("raw_upstream_value"),
                "provenance": {
                    "source_url": ov.get("source_url", ""),
                    "checked_on": ov.get("added", ""),
                    "market": ov.get("market", "See source note"),
                    "model_codes": ov.get("model_codes", []),
                    "note": ov.get("source_note", ""),
                },
            }
            if ov.get("list_qualifier") is not None:
                by_id[oid]["support_window"]["provenance"]["list_qualifier"] = (
                    ov["list_qualifier"]
                )

        if oid in unresolved_ids:
            reviewed_basis = basis == "manufacturer_exact"
            if basis == "manufacturer_month_end" and isinstance(eol_value, str):
                try:
                    parsed_eol = date.fromisoformat(eol_value)
                    reviewed_basis = (
                        parsed_eol.day
                        == monthrange(parsed_eol.year, parsed_eol.month)[1]
                    )
                except ValueError:
                    reviewed_basis = False
            sourced_security_date = (
                isinstance(eol_value, str)
                and bool(eol_value.strip())
                and reviewed_basis
                and isinstance(ov.get("source_url"), str)
                and ov["source_url"].startswith("https://")
                and isinstance(ov.get("source_note"), str)
                and bool(ov["source_note"].strip())
            )
            if sourced_security_date:
                cleared_ids.add(oid)
                print(f"  * PROVENANCE resolved: {oid} from {ov['source_url']}")
            else:
                print(
                    f"[WARN] override {oid}: unresolved security provenance; "
                    "requires eol, manufacturer_exact or a true "
                    "manufacturer_month_end date, source_url, and source_note")

    if semantic_failures is not None and cleared_ids:
        semantic_failures[:] = [
            failure for failure in semantic_failures
            if failure["id"] not in cleared_ids
        ]
    print(f"  * {applied} override(s) applied")
    return sorted(by_id.values(), key=lambda x: x["released"], reverse=True)


# ---------------------------------------------------------------- validation gate (P1)
def validate(devices: list, existing: dict) -> list:
    """Return a list of failure strings. Empty list = all gates pass."""
    fails = []

    # Gate 1: absolute count sanity
    n = len(devices)
    if n < MIN_DEVICES:
        fails.append(f"count {n} below floor {MIN_DEVICES}")
    if n > MAX_DEVICES:
        fails.append(f"count {n} above ceiling {MAX_DEVICES}")

    # Gate 2: ±10% tripwire vs the currently-published file
    if existing:
        prev = len(existing)
        if prev and abs(n - prev) / prev > COUNT_TRIPWIRE:
            fails.append(
                f"count moved {prev} -> {n} "
                f"({(n - prev) / prev:+.0%}), tripwire is ±{COUNT_TRIPWIRE:.0%}")

    # Gate 3: per-record schema
    seen_ids = set()
    for d in devices:
        did = d.get("id", "<no id>")
        for f in REQUIRED_FIELDS:
            if not isinstance(d.get(f), str) or not d[f].strip():
                fails.append(f"{did}: field '{f}' missing/empty")
        if did in seen_ids:
            fails.append(f"duplicate id: {did}")
        seen_ids.add(did)
        for f in ("released", "eol"):
            v = d.get(f)
            if isinstance(v, str):
                try:
                    datetime.fromisoformat(v)
                except ValueError:
                    fails.append(f"{did}: {f} '{v}' is not an ISO date")
        try:
            if datetime.fromisoformat(d["eol"]) <= datetime.fromisoformat(d["released"]):
                fails.append(f"{did}: eol {d['eol']} not after released {d['released']}")
        except (KeyError, TypeError, ValueError):
            pass  # already reported above
        if d.get("brand") == "Google" or "support_window" in d:
            for failure in validate_support_window(d):
                fails.append(f"{did}: support metadata: {failure}")

    # Gate 4: brand mix
    for brand, floor in MIN_PER_BRAND.items():
        got = sum(1 for d in devices if d.get("brand") == brand)
        if got < floor:
            fails.append(f"brand {brand}: only {got} devices (floor {floor})")

    # Gate 5: canaries
    by_id = {d["id"]: d for d in devices}
    for cid, released in CANARIES.items():
        if cid not in by_id:
            fails.append(f"canary missing: {cid}")
        elif by_id[cid]["released"] != released:
            fails.append(
                f"canary {cid}: released changed "
                f"{released} -> {by_id[cid]['released']}")
    return fails


# ---------------------------------------------------------------- main
def main() -> int:
    dry_run = "--dry-run" in sys.argv
    existing = load_existing()

    devices = []
    semantic_failures = []
    for brand, endpoint in SOURCES.items():
        try:
            devices += normalize(brand, fetch(endpoint), semantic_failures)
        except Exception as e:  # one source failing shouldn't kill the run
            print(f"[WARN] {brand} fetch failed: {e} — keeping existing entries")
            devices += [d for d in existing.values() if d["brand"] == brand]

    # De-dupe on id, newest release first
    seen, deduped = set(), []
    for d in sorted(devices, key=lambda x: x["released"], reverse=True):
        if d["id"] not in seen:
            seen.add(d["id"])
            deduped.append(d)

    # Manual corrections merge LAST (P1)
    deduped = apply_overrides(deduped, semantic_failures)
    deduped = apply_pixel_support_metadata(deduped, semantic_failures)
    seen = {d["id"] for d in deduped}

    # Diff report — this becomes your monthly changelog / newsletter fodder
    new_ids = seen - set(existing)
    changed = [
        d["id"] for d in deduped
        if d["id"] in existing and existing[d["id"]]["eol"] != d["eol"]
    ]
    today = date.today().isoformat()
    print(f"[{today}] {len(deduped)} devices | {len(new_ids)} new | {len(changed)} EOL changes")
    for i in sorted(new_ids):
        print(f"  + NEW: {i}")
    for i in changed:
        print(f"  ~ EOL CHANGED: {i}: {existing[i]['eol']} -> "
              f"{next(d['eol'] for d in deduped if d['id'] == i)}")

    # Devices whose stated window ends within 12 months — content/alert opportunities.
    # Precision-aware Pixel records must not be classified from the legacy eol day.
    soon = []
    for d in deduped:
        try:
            if support_state(d, date.today()) == "ending":
                soon.append(d)
        except (KeyError, ValueError, TypeError):
            pass
    print(f"  ! {len(soon)} devices have a stated support window ending within 12 months "
          "(alert/content targets)")

    # ---------------- VALIDATION GATE: fail = no write, non-zero exit ----------------
    fails = validate(deduped, existing)
    fails.extend(
        f"semantic provenance: {failure['message']}"
        for failure in semantic_failures)
    if fails:
        print(f"\n[FAIL] {len(fails)} validation gate failure(s) — devices.json NOT written:")
        for f in fails:
            print(f"  ✗ {f}")
        print("[FAIL] Previous devices.json remains live. Investigate before re-running.")
        return 1
    print("[GATE] all validation gates passed "
          f"({len(deduped)} devices, canaries OK, schema OK)")

    if dry_run:
        print("[DRY RUN] devices.json not written")
        return 0

    OUTPUT.write_text(json.dumps({
        "schema_version": "1.1",
        "generated": today,
        "source_note": "Support evidence preserves source precision and meaning. Pixel policy "
                       "windows are month-level minimum guarantees, with exact-looking upstream "
                       "dates retained only for compatibility. Reviewed Samsung corrections preserve "
                       "their declared day or month precision; other explicit endoflife.date security "
                       "dates remain day-shaped until their own precision audit. Android-upgrade dates "
                       "are never substituted. "
                       "Auto-generated — do not hand-edit.",
        "devices": deduped,
    }, indent=1), encoding="utf-8")
    print(f"[OK] wrote {OUTPUT} ({len(deduped)} devices)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
