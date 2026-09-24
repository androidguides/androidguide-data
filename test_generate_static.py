import json
from pathlib import Path
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

import generate_static
from generate_static import is_ended, sentence
from support_status import support_date_text, support_sentence, support_state


class EolBoundaryTests(unittest.TestCase):
    A23 = {
        "id": "samsung-galaxy-a23-5g",
        "brand": "Samsung",
        "model": "Galaxy A23 5G",
        "released": "2022-09-02",
        "eol": "2026-09-30",
    }
    PIXEL_6 = {
        "id": "google-pixel-6",
        "brand": "Google",
        "model": "Pixel 6",
        "released": "2021-10-28",
        "eol": "2026-10-01",
    }

    def test_eol_date_is_still_supported(self):
        self.assertFalse(is_ended(date(2026, 9, 30), date(2026, 9, 30)))
        self.assertFalse(is_ended(date(2026, 10, 1), date(2026, 10, 1)))

    def test_status_changes_the_day_after_eol(self):
        self.assertTrue(is_ended(date(2026, 9, 30), date(2026, 10, 1)))
        self.assertTrue(is_ended(date(2026, 10, 1), date(2026, 10, 2)))

    def test_sentence_uses_the_same_boundary(self):
        self.assertIn("are scheduled to end on", sentence(self.A23, date(2026, 9, 30)))
        self.assertIn("ended on", sentence(self.A23, date(2026, 10, 1)))
        self.assertIn("are scheduled to end on", sentence(self.PIXEL_6, date(2026, 10, 1)))
        self.assertIn("ended on", sentence(self.PIXEL_6, date(2026, 10, 2)))

    def test_sentence_links_to_the_canonical_device_page(self):
        rendered = sentence(self.A23, date(2026, 9, 30))
        self.assertIn(
            '<a href="/device/samsung-galaxy-a23-5g/">Samsung Galaxy A23 5G</a>',
            rendered,
        )


class PrecisionAwareStatusTests(unittest.TestCase):
    PIXEL_6 = {
        "id": "google-pixel-6",
        "brand": "Google",
        "model": "Pixel 6",
        "released": "2021-10-28",
        "eol": "2026-10-01",
        "support_window": {
            "published_value": "2026-10",
            "precision": "month",
            "basis": "policy_calculation",
            "meaning": "minimum_guarantee",
        },
        "support_observation": {"status": "listed_under_current_policy"},
    }
    PIXEL_5 = {
        "brand": "Google",
        "model": "Pixel 5",
        "released": "2020-10-15",
        "eol": "2023-11-05",
        "support_window": {
            "published_value": None,
            "precision": "unknown",
            "basis": "aggregator",
            "meaning": "estimate",
        },
        "support_observation": {"status": "no_longer_receives_updates"},
    }
    PIXEL_UNVERIFIED = {
        "brand": "Google",
        "model": "Pixel Example",
        "released": "2020-10-15",
        "eol": "2023-11-05",
        "support_window": {
            "published_value": None,
            "precision": "unknown",
            "basis": "aggregator",
            "meaning": "estimate",
            "raw_upstream_value": "2023-11-05",
            "provenance": {
                "source_url": "https://endoflife.date/api/pixel.json",
                "checked_on": "2026-09-11",
                "market": "US",
                "model_codes": [],
                "note": "No current observation settles this record's support state.",
            },
        },
    }

    def test_policy_month_is_not_converted_to_an_exact_day(self):
        self.assertEqual("ending", support_state(self.PIXEL_6, date(2026, 10, 31)))
        self.assertEqual(
            "October 2026 — exact end date not specified",
            support_date_text(self.PIXEL_6),
        )
        text = support_sentence(self.PIXEL_6, date(2026, 10, 31))
        self.assertIn("ends this month", text)
        self.assertNotIn("October 1", text)

    def test_day_after_policy_month_is_guarantee_elapsed_not_confirmed_ended(self):
        self.assertEqual(
            "guarantee_elapsed",
            support_state(self.PIXEL_6, date(2026, 11, 1)),
        )
        text = support_sentence(self.PIXEL_6, date(2026, 11, 1))
        self.assertIn("guarantee period", text)
        self.assertIn("has elapsed", text)
        self.assertNotIn("stopped", text)
        self.assertNotIn("ended on", text)

    def test_historical_observation_does_not_invent_a_cutoff_date(self):
        self.assertEqual("ended", support_state(self.PIXEL_5, date(2026, 9, 11)))
        text = support_sentence(self.PIXEL_5, date(2026, 9, 11))
        self.assertIn("no longer receives", text)
        self.assertIn("exact historical cutoff date is not established", text)
        self.assertNotIn("November 5", text)

    def test_unknown_precision_without_observation_stays_unknown(self):
        self.assertEqual(
            "unknown",
            support_state(self.PIXEL_UNVERIFIED, date(2026, 9, 11)),
        )
        text = support_sentence(self.PIXEL_UNVERIFIED, date(2026, 9, 11))
        self.assertIn("status", text)
        self.assertIn("not established", text)
        self.assertNotIn("November 5", text)
        self.assertNotIn("ended on", text)

    def test_unknown_precision_with_current_listing_is_supported_without_a_date(self):
        record = json.loads(json.dumps(self.PIXEL_UNVERIFIED))
        record["support_observation"] = {
            "status": "listed_under_current_policy",
        }

        self.assertEqual("supported", support_state(record, date(2026, 9, 24)))
        text = support_sentence(record, date(2026, 9, 24))
        self.assertIn("current manufacturer evidence", text.lower())
        self.assertIn("lists", text)
        self.assertIn("exact support-end date is not published", text)
        self.assertNotIn("November 5", text)

    def test_up_to_month_is_not_rendered_as_a_guarantee_or_endpoint(self):
        record = json.loads(json.dumps(self.PIXEL_6))
        record["brand"] = "Samsung"
        record["model"] = "Galaxy A54 5G"
        record["eol"] = "2028-04-01"
        record["support_window"].update({
            "published_value": "2028-04",
            "meaning": "up_to",
            "raw_upstream_value": "2028-03-24",
        })

        self.assertEqual("supported", support_state(record, date(2026, 9, 24)))
        text = support_sentence(record, date(2026, 9, 24))
        self.assertIn("may run up to April 2028", text)
        self.assertIn("exact endpoint is not published", text)
        self.assertNotIn("guaranteed", text.lower())
        self.assertNotIn("scheduled", text.lower())

        self.assertEqual("unknown", support_state(record, date(2028, 5, 1)))
        later = support_sentence(record, date(2028, 5, 1))
        self.assertIn("current support status is not established", later)
        self.assertNotIn("Current manufacturer evidence lists", later)

    def test_month_precision_with_ended_observation_prioritizes_current_state(self):
        record = json.loads(json.dumps(self.PIXEL_6))
        record["support_observation"]["status"] = "no_longer_receives_updates"
        text = support_sentence(record, date(2026, 12, 2))
        self.assertEqual("ended", support_state(record, date(2026, 12, 2)))
        self.assertIn("no longer receives", text)
        self.assertIn("October 2026", text)
        self.assertIn("exact stop day is not established", text)
        self.assertNotIn("ends in", text)
        self.assertNotIn("ends this month", text)

    def test_day_precision_with_ended_observation_does_not_invent_stop_day(self):
        record = {
            "brand": "Samsung",
            "model": "Galaxy Example",
            "released": "2025-01-01",
            "eol": "2030-12-31",
            "support_window": {
                "published_value": "2030-12-31",
                "precision": "day",
                "basis": "manufacturer_published",
                "meaning": "scheduled_endpoint",
            },
            "support_observation": {"status": "removed_from_support_scope"},
        }
        text = support_sentence(record, date(2026, 9, 13))
        self.assertEqual("ended", support_state(record, date(2026, 9, 13)))
        self.assertIn("no longer receives", text)
        self.assertIn("published support date", text)
        self.assertIn("does not establish the exact stop day", text)
        self.assertNotIn("ended on", text)

    def test_regional_override_list_sentence_keeps_qualifier_with_date(self):
        record = {
            "id": "samsung-galaxy-a37-5g",
            "brand": "Samsung",
            "model": "Galaxy A37 5G",
            "released": "2026-04-10",
            "eol": "2032-03-31",
            "source": "override",
            "support_window": {
                "published_value": "2032-03-31",
                "precision": "day",
                "basis": "manufacturer_published",
                "meaning": "scheduled_endpoint",
                "raw_upstream_value": "2032-04-10",
                "provenance": {
                    "list_qualifier": (
                        "Samsung SM-A376W/B — no US endpoint published"
                    ),
                },
            },
        }

        rendered = sentence(record, date(2026, 9, 11))

        self.assertIn("March 31, 2032", rendered)
        self.assertIn(
            '<span class="source-scope">Samsung SM-A376W/B — '
            "no US endpoint published</span>",
            rendered,
        )


class StaticGenerationDateTests(unittest.TestCase):
    def test_generated_date_controls_status_and_visible_as_of_date(self):
        record = json.loads(json.dumps(PrecisionAwareStatusTests.PIXEL_6))
        record["support_window"]["published_value"] = "2099-10"
        record["eol"] = "2099-10-01"
        payload = {
            "schema_version": "1.1",
            "generated": "2099-10-15",
            "devices": [record],
        }
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "devices.json"
            output = Path(tempdir) / "devices-static.html"
            source.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(generate_static, "INPUT", source), patch.object(
                generate_static, "OUTPUT", output
            ):
                self.assertEqual(0, generate_static.main())
            rendered = output.read_text(encoding="utf-8")
        self.assertIn("As of October 15, 2099", rendered)
        self.assertIn("ends this month", rendered)
        self.assertNotIn("has elapsed", rendered)


if __name__ == "__main__":
    unittest.main()
