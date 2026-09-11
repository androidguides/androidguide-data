import json
from pathlib import Path
import unittest

from support_contract import validate_support_window


ROOT = Path(__file__).resolve().parent
AUDIT = json.loads((ROOT / "pixel-support-audit.json").read_text(encoding="utf-8"))
DATASET = json.loads((ROOT / "devices.json").read_text(encoding="utf-8"))
POLICY_URL = AUDIT["sources"]["current_policy"]
AVAILABILITY_URL = AUDIT["sources"]["us_availability"]
UPSTREAM_URL = AUDIT["sources"]["upstream_feed"]


class PixelSupportAuditTests(unittest.TestCase):
    def test_audit_covers_every_current_pixel_exactly_once(self):
        pixel_ids = {
            item["id"] for item in DATASET["devices"] if item["brand"] == "Google"
        }
        audited_ids = [item["id"] for item in AUDIT["records"]]

        self.assertEqual(38, len(pixel_ids))
        self.assertEqual(38, len(audited_ids))
        self.assertEqual(len(audited_ids), len(set(audited_ids)))
        self.assertEqual(pixel_ids, set(audited_ids))

    def test_group_counts_and_declared_total_are_literal(self):
        counts = {
            group: sum(item["group"] == group for item in AUDIT["records"])
            for group in AUDIT["groups"]
        }

        self.assertEqual(38, AUDIT["record_count"])
        self.assertEqual(24, counts["current_policy"])
        self.assertEqual(14, counts["historical_status_only"])
        self.assertEqual(AUDIT["groups"]["current_policy"]["count"], counts["current_policy"])
        self.assertEqual(
            AUDIT["groups"]["historical_status_only"]["count"],
            counts["historical_status_only"],
        )

    def test_current_policy_months_are_derived_from_official_availability(self):
        for item in AUDIT["records"]:
            if item["group"] != "current_policy":
                continue
            year, month = map(int, item["availability_month"].split("-"))
            expected = f"{year + item['policy_years']:04d}-{month:02d}"
            with self.subTest(device=item["id"]):
                self.assertEqual(expected, item["published_value"])
                self.assertEqual(expected, item["legacy_eol"][:7])
                self.assertEqual("01", item["legacy_eol"][8:10])

    def test_every_audit_result_satisfies_the_contract(self):
        current_by_id = {item["id"]: item for item in DATASET["devices"]}
        for item in AUDIT["records"]:
            source_record = current_by_id[item["id"]]
            if item["group"] == "current_policy":
                window = {
                    "published_value": item["published_value"],
                    "precision": "month",
                    "basis": "policy_calculation",
                    "meaning": "minimum_guarantee",
                    "raw_upstream_value": item["legacy_eol"],
                    "provenance": self._provenance(
                        POLICY_URL,
                        "Google's policy duration is calculated from the model's Google Store US availability month at "
                        + AVAILABILITY_URL,
                    ),
                }
                observation_status = "listed_under_current_policy"
                observation_note = "Google currently lists this model under its update policy."
            else:
                window = {
                    "published_value": None,
                    "precision": "unknown",
                    "basis": "aggregator",
                    "meaning": "estimate",
                    "raw_upstream_value": item["legacy_eol"],
                    "provenance": self._provenance(
                        UPSTREAM_URL,
                        "The raw exact-looking date is retained as an aggregator input, not attributed to Google.",
                    ),
                }
                observation_status = "no_longer_receives_updates"
                observation_note = "Google currently lists this model as no longer receiving OS or security updates."

            candidate = dict(source_record)
            candidate["support_window"] = window
            candidate["support_observation"] = {
                "status": observation_status,
                "observed_on": "2026-09-11",
                "provenance": self._provenance(POLICY_URL, observation_note),
            }
            with self.subTest(device=item["id"]):
                self.assertEqual([], validate_support_window(candidate))

    def test_known_source_conflicts_are_not_hidden(self):
        by_id = {item["id"]: item for item in AUDIT["records"]}

        self.assertIn("current US availability table says October", by_id["google-pixel-4a-5g"]["note"])
        self.assertIn("November 2023 update", by_id["google-pixel-5"]["note"])

    @staticmethod
    def _provenance(source_url, note):
        return {
            "source_url": source_url,
            "checked_on": "2026-09-11",
            "market": "US",
            "model_codes": [],
            "note": note,
        }


if __name__ == "__main__":
    unittest.main()
