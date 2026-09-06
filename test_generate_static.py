import unittest
from datetime import date

from generate_static import is_ended, sentence


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


if __name__ == "__main__":
    unittest.main()
