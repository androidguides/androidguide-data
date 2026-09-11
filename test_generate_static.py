import unittest
from datetime import date

from generate_static import is_ended, sentence
from support_status import support_date_text, support_sentence, support_state


class EolBoundaryTests(unittest.TestCase):
    A23 = {
        "brand": "Samsung",
        "model": "Galaxy A23 5G",
        "released": "2022-09-02",
        "eol": "2026-09-30",
    }
    PIXEL_6 = {
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


class PrecisionAwareStatusTests(unittest.TestCase):
    PIXEL_6 = {
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
        self.assertIn("no longer receiving", text)
        self.assertIn("exact historical cutoff date is not established", text)
        self.assertNotIn("November 5", text)


if __name__ == "__main__":
    unittest.main()
