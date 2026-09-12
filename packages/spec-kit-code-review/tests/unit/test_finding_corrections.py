"""Focused parser contract for lossless category recovery."""

import unittest

from spec_kit_code_review.errors import AppError
from spec_kit_code_review.finding_corrections import parse_bytes


class CorrectionTests(unittest.TestCase):

    def test_duplicate_keys_fail_closed(self):
        with self.assertRaises(AppError):
            parse_bytes(b'{"findings":[],"findings":[]}')
