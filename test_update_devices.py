import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from update_devices import apply_overrides, apply_pixel_support_metadata, normalize


class NormalizeSecurityEolTests(unittest.TestCase):
    def test_support_date_is_not_substituted_for_missing_security_eol(self):
        raw = [{
            "cycle": "galaxy-a23-5g",
            "releaseLabel": "Galaxy A23 5G",
            "releaseDate": "2022-09-02",
            "eol": False,
            "support": "2025-09-02",
        }]

        output = io.StringIO()
        semantic_failures = []
        with redirect_stdout(output):
            devices = normalize("Samsung", raw, semantic_failures)

        self.assertEqual([], devices)
        self.assertIn("support date cannot substitute", output.getvalue())
        self.assertEqual(1, len(semantic_failures))
        self.assertEqual("samsung-galaxy-a23-5g", semantic_failures[0]["id"])
        self.assertIn("Galaxy A23 5G", semantic_failures[0]["message"])

    def test_out_of_scope_support_only_record_does_not_trip_guard(self):
        raw = [{
            "cycle": "galaxy-m99",
            "releaseLabel": "Galaxy M99",
            "releaseDate": "2026-01-01",
            "eol": False,
            "support": "2030-01-01",
        }]
        semantic_failures = []

        devices = normalize("Samsung", raw, semantic_failures)

        self.assertEqual([], devices)
        self.assertEqual([], semantic_failures)

    def test_explicit_security_eol_is_retained(self):
        raw = [{
            "cycle": "galaxy-s24",
            "releaseLabel": "Galaxy S24",
            "releaseDate": "2024-01-24",
            "eol": "2031-01-24",
            "support": "2031-01-24",
        }]

        self.assertEqual(
            [{
                "id": "samsung-galaxy-s24",
                "brand": "Samsung",
                "model": "Galaxy S24",
                "released": "2024-01-24",
                "eol": "2031-01-24",
                "source": "endoflife.date",
            }],
            normalize("Samsung", raw),
        )


class OverrideProvenanceTests(unittest.TestCase):
    RAW_A23 = [{
        "cycle": "galaxy-a23-5g",
        "releaseLabel": "Galaxy A23 5G",
        "releaseDate": "2022-09-02",
        "eol": False,
        "support": "2025-09-02",
    }]

    A23_FIELDS = {
        "brand": "Samsung",
        "model": "Galaxy A23 5G",
        "released": "2022-09-02",
        "eol": "2026-09-30",
    }

    def normalize_a23(self):
        failures = []
        devices = normalize("Samsung", self.RAW_A23, failures)
        return devices, failures

    def sourced_override(self, **changes):
        override = {
            "id": "samsung-galaxy-a23-5g",
            "add": True,
            "fields": self.A23_FIELDS.copy(),
            "security_eol_basis": "manufacturer_exact",
            "market": "UK publication; US-sold model scope",
            "source_url": "https://www.samsung.com/uk/example",
            "source_note": "Samsung UK publishes the exact security deadline.",
            "reason": "Manufacturer-backed correction.",
        }
        override.update(changes)
        return override

    def test_matching_sourced_date_clears_guard(self):
        devices, failures = self.normalize_a23()

        result = apply_overrides(
            devices, failures, entries=[self.sourced_override()])

        self.assertEqual([], failures)
        self.assertEqual("2026-09-30", result[0]["eol"])
        self.assertEqual("override", result[0]["source"])
        self.assertEqual("day", result[0]["support_window"]["precision"])
        self.assertEqual(
            "UK publication; US-sold model scope",
            result[0]["support_window"]["provenance"]["market"],
        )

    def test_missing_provenance_does_not_clear_guard(self):
        devices, failures = self.normalize_a23()

        result = apply_overrides(
            devices,
            failures,
            entries=[self.sourced_override(source_url=None)],
        )

        self.assertEqual(1, len(failures))
        self.assertEqual("2026-09-30", result[0]["eol"])

    def test_unrelated_override_does_not_clear_guard(self):
        devices, failures = self.normalize_a23()
        unrelated = self.sourced_override(
            id="samsung-galaxy-z-fold8",
            fields={
                "brand": "Samsung",
                "model": "Galaxy Z Fold8",
                "released": "2026-08-07",
                "eol": "2033-07-31",
            },
        )

        apply_overrides(devices, failures, entries=[unrelated])

        self.assertEqual(1, len(failures))
        self.assertEqual("samsung-galaxy-a23-5g", failures[0]["id"])

    def test_explicit_exclusion_clears_matching_guard(self):
        devices, failures = self.normalize_a23()

        result = apply_overrides(devices, failures, entries=[{
            "id": "samsung-galaxy-a23-5g",
            "remove": True,
            "reason": "Explicitly exclude until a security date is published.",
        }])

        self.assertEqual([], failures)
        self.assertEqual([], result)

    def test_a37_and_a57_overrides_replace_only_the_two_anniversary_dates(self):
        root = Path(__file__).parent
        current = json.loads(
            (root / "devices.json").read_text(encoding="utf-8")
        )["devices"]
        overrides = json.loads(
            (root / "overrides.json").read_text(encoding="utf-8")
        )["overrides"]
        before = {item["id"]: item["eol"] for item in current}

        result = apply_overrides(
            [dict(item) for item in current], entries=overrides
        )
        after = {item["id"]: item["eol"] for item in result}
        changed = sorted(
            device_id for device_id in before if before[device_id] != after[device_id]
        )

        self.assertEqual(
            ["samsung-galaxy-a37-5g", "samsung-galaxy-a57-5g"],
            changed,
        )
        for device_id, qualifier in (
            (
                "samsung-galaxy-a37-5g",
                "Samsung SM-A376W/B — no US endpoint published",
            ),
            (
                "samsung-galaxy-a57-5g",
                "Samsung SM-A576W/B — no US endpoint published",
            ),
        ):
            record = next(item for item in result if item["id"] == device_id)
            window = record["support_window"]
            self.assertEqual("2032-03-31", record["eol"])
            self.assertNotEqual("2032-04-10", record["eol"])
            self.assertEqual("override", record["source"])
            self.assertEqual("day", window["precision"])
            self.assertEqual("2032-04-10", window["raw_upstream_value"])
            self.assertEqual(qualifier, window["provenance"]["list_qualifier"])


class PixelSupportMetadataTests(unittest.TestCase):
    ROOT = Path(__file__).parent

    def setUp(self):
        self.audit = json.loads(
            (self.ROOT / "pixel-support-audit.json").read_text(encoding="utf-8")
        )
        current = json.loads(
            (self.ROOT / "devices.json").read_text(encoding="utf-8")
        )["devices"]
        self.pixels = [dict(device) for device in current if device["brand"] == "Google"]

    def test_all_current_pixels_receive_reviewed_metadata(self):
        failures = []
        result = apply_pixel_support_metadata(self.pixels, failures, self.audit)

        self.assertEqual(38, len(result))
        self.assertEqual([], failures)
        self.assertTrue(all("support_window" in item for item in result))
        self.assertTrue(all("support_observation" in item for item in result))

    def test_unaudited_new_pixel_blocks_publication(self):
        devices = self.pixels + [{
            "id": "google-pixel-12",
            "brand": "Google",
            "model": "Pixel 12",
            "released": "2027-08-20",
            "eol": "2034-08-01",
            "source": "endoflife.date",
        }]
        failures = []

        apply_pixel_support_metadata(devices, failures, self.audit)

        self.assertTrue(any(
            item["id"] == "google-pixel-12" and "no reviewed" in item["message"]
            for item in failures
        ))

    def test_audited_field_drift_blocks_publication(self):
        devices = [dict(device) for device in self.pixels]
        pixel_6 = next(item for item in devices if item["id"] == "google-pixel-6")
        pixel_6["eol"] = "2026-10-31"
        failures = []

        apply_pixel_support_metadata(devices, failures, self.audit)

        self.assertTrue(any(
            item["id"] == "google-pixel-6" and "eol" in item["message"]
            for item in failures
        ))


if __name__ == "__main__":
    unittest.main()
