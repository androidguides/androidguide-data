import unittest

from support_contract import exact_end_date, validate_support_window


def record(window):
    return {
        "id": "test-device",
        "brand": "Test",
        "model": "Device",
        "released": "2021-01-01",
        "eol": "2026-10-01",
        "source": "endoflife.date",
        "support_window": window,
    }


def provenance(**changes):
    value = {
        "source_url": "https://example.com/support",
        "checked_on": "2026-09-11",
        "market": "US",
        "model_codes": [],
        "note": "Source supplies a support commitment, not an observed final patch.",
    }
    value.update(changes)
    return value


class SupportWindowContractTests(unittest.TestCase):
    def test_pixel_month_minimum_guarantee_is_valid_without_an_exact_day(self):
        item = record({
            "published_value": "2026-10",
            "precision": "month",
            "basis": "policy_calculation",
            "meaning": "minimum_guarantee",
            "raw_upstream_value": "2026-10-01",
            "provenance": provenance(),
        })

        self.assertEqual([], validate_support_window(item))
        self.assertIsNone(exact_end_date(item))

    def test_exact_manufacturer_endpoint_can_expose_an_exact_day(self):
        item = record({
            "published_value": "2026-09-30",
            "precision": "day",
            "basis": "manufacturer_published",
            "meaning": "scheduled_endpoint",
            "raw_upstream_value": False,
            "provenance": provenance(
                source_url="https://www.samsung.com/uk/example",
                market="UK",
                model_codes=["SM-A236B"],
            ),
        })
        item["eol"] = "2026-09-30"
        item["source"] = "override"

        self.assertEqual([], validate_support_window(item))
        self.assertEqual("2026-09-30", exact_end_date(item).isoformat())

    def test_optional_list_qualifier_is_valid_and_raw_upstream_may_be_null(self):
        item = record({
            "published_value": "2026-09-30",
            "precision": "day",
            "basis": "manufacturer_published",
            "meaning": "scheduled_endpoint",
            "raw_upstream_value": None,
            "provenance": provenance(
                list_qualifier="Samsung regional endpoint — no US endpoint published",
            ),
        })
        item["eol"] = "2026-09-30"
        item["source"] = "override"

        self.assertEqual([], validate_support_window(item))

    def test_existing_record_without_optional_list_qualifier_remains_valid(self):
        item = record({
            "published_value": "2026-09-30",
            "precision": "day",
            "basis": "manufacturer_published",
            "meaning": "scheduled_endpoint",
            "raw_upstream_value": None,
            "provenance": provenance(),
        })
        item["eol"] = "2026-09-30"
        item["source"] = "override"

        self.assertEqual([], validate_support_window(item))

    def test_list_qualifier_cannot_be_empty(self):
        item = record({
            "published_value": "2026-09-30",
            "precision": "day",
            "basis": "manufacturer_published",
            "meaning": "scheduled_endpoint",
            "raw_upstream_value": "2026-10-01",
            "provenance": provenance(list_qualifier=""),
        })
        item["eol"] = "2026-09-30"
        item["source"] = "override"

        self.assertIn(
            "provenance.list_qualifier must be a non-empty string",
            validate_support_window(item),
        )

    def test_unknown_precision_cannot_smuggle_in_a_day_or_bounds(self):
        item = record({
            "published_value": "2026-10-01",
            "precision": "unknown",
            "basis": "aggregator",
            "meaning": "estimate",
            "raw_upstream_value": "2026-10-01",
            "provenance": provenance(),
        })

        failures = validate_support_window(item)
        self.assertIn(
            "unknown precision requires null published_value",
            failures,
        )
        self.assertIsNone(exact_end_date(item))

    def test_month_value_does_not_create_an_exact_endpoint(self):
        item = record({
            "published_value": "2026-10",
            "precision": "month",
            "basis": "policy_calculation",
            "meaning": "minimum_guarantee",
            "raw_upstream_value": "2026-10-01",
            "provenance": provenance(),
        })

        self.assertEqual([], validate_support_window(item))
        self.assertIsNone(exact_end_date(item))

    def test_observation_is_not_a_support_window_basis(self):
        item = record({
            "published_value": "2026-10",
            "precision": "month",
            "basis": "observed_scope_removal",
            "meaning": "minimum_guarantee",
            "raw_upstream_value": "2026-10-01",
            "provenance": provenance(),
        })

        self.assertIn(
            "basis must be one of ['aggregator', 'manufacturer_published', 'policy_calculation']",
            validate_support_window(item),
        )

    def test_support_observation_can_coexist_with_a_guarantee_window(self):
        item = record({
            "published_value": "2026-10",
            "precision": "month",
            "basis": "policy_calculation",
            "meaning": "minimum_guarantee",
            "raw_upstream_value": "2026-10-01",
            "provenance": provenance(),
        })
        item["support_observation"] = {
            "status": "listed_under_current_policy",
            "observed_on": "2026-09-11",
            "provenance": provenance(
                note="Google currently lists this model under its update policy."
            ),
        }

        self.assertEqual([], validate_support_window(item))

    def test_observation_requires_its_own_date_and_provenance(self):
        item = record({
            "published_value": None,
            "precision": "unknown",
            "basis": "aggregator",
            "meaning": "estimate",
            "raw_upstream_value": "2023-11-05",
            "provenance": provenance(),
        })
        item["support_observation"] = {
            "status": "no_longer_receives_updates",
            "observed_on": "not-a-date",
            "provenance": provenance(source_url="http://example.com/status"),
        }

        failures = validate_support_window(item)
        self.assertIn("support_observation.observed_on must be an ISO date string", failures)
        self.assertIn(
            "support_observation.provenance.source_url must be HTTPS",
            failures,
        )

    def test_provenance_requires_https_date_market_models_and_note(self):
        item = record({
            "published_value": "2026-10",
            "precision": "month",
            "basis": "policy_calculation",
            "meaning": "minimum_guarantee",
            "raw_upstream_value": "2026-10-01",
            "provenance": provenance(
                source_url="http://example.com/support",
                checked_on="September 11",
                market="",
                model_codes=[""],
                note="",
            ),
        })

        failures = validate_support_window(item)
        self.assertIn("provenance.source_url must be HTTPS", failures)
        self.assertIn("provenance.checked_on must be an ISO date string", failures)
        self.assertIn("provenance.market must be a non-empty string", failures)
        self.assertIn(
            "provenance.model_codes must be a list of non-empty strings",
            failures,
        )
        self.assertIn("provenance.note must be a non-empty string", failures)

    def test_generated_source_vocabulary_does_not_expand(self):
        item = record({
            "published_value": "2026-10",
            "precision": "month",
            "basis": "policy_calculation",
            "meaning": "minimum_guarantee",
            "raw_upstream_value": "2026-10-01",
            "provenance": provenance(),
        })
        item["source"] = "manufacturer"

        self.assertIn(
            "source must remain 'endoflife.date' or 'override'",
            validate_support_window(item),
        )


if __name__ == "__main__":
    unittest.main()
