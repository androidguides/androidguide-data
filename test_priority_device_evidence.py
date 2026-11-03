"""Guard the three reviewed corrections against unrelated data changes."""
import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

from update_devices import apply_overrides, apply_pixel_support_metadata, validate
from support_status import support_state, support_date_text

ROOT = Path(__file__).parent


class PriorityEvidenceTests(unittest.TestCase):
    def test_reviewed_overrides_preserve_other_records_and_precision(self):
        original = json.loads((ROOT / 'devices.json').read_text(encoding='utf-8'))['devices']
        before = {d['id']: d for d in original}
        failures = []
        with redirect_stdout(io.StringIO()):
            result = apply_overrides(copy.deepcopy(original), failures)
            result = apply_pixel_support_metadata(result, failures)
        self.assertEqual([], failures)
        self.assertEqual([], validate(result, before))
        after = {d['id']: d for d in result}
        targets = {'samsung-galaxy-s24', 'samsung-galaxy-s25', 'google-pixel-8'}
        self.assertEqual(set(before), set(after))
        for key in set(before) - targets:
            self.assertEqual(before[key], after[key], key)
        self.assertEqual('2024-01-31', after['samsung-galaxy-s24']['released'])
        self.assertEqual('2025-02-07', after['samsung-galaxy-s25']['released'])
        self.assertEqual('2023-10-12', after['google-pixel-8']['released'])
        self.assertEqual('January 2031 — exact end date not specified', support_date_text(after['samsung-galaxy-s24']))
        self.assertEqual('January 31, 2032', support_date_text(after['samsung-galaxy-s25']))
        self.assertEqual('October 2030 — exact end date not specified', support_date_text(after['google-pixel-8']))
        self.assertEqual('ending', support_state(after['samsung-galaxy-s24'], date(2031, 1, 31)))
        self.assertEqual('guarantee_elapsed', support_state(after['samsung-galaxy-s24'], date(2031, 2, 1)))
        self.assertEqual('ending', support_state(after['samsung-galaxy-s25'], date(2032, 1, 31)))
        self.assertEqual('ended', support_state(after['samsung-galaxy-s25'], date(2032, 2, 1)))


if __name__ == '__main__':
    unittest.main()
