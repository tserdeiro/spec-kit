from __future__ import annotations

import hashlib
import unittest

from spec_kit_code_review.coverage import validate
from spec_kit_code_review.git import open_git
from tests.support.repo import TemporaryRepository


class CoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = "uno\r\ndos 🙈\r\ntres\r\n"
        self.inventory = {
            "sources": [{"path": "docs/a.md", "version": "head", "sha256": hashlib.sha256(self.text.encode()).hexdigest()}],
            "required": [{"path": "docs/a.md", "start": 1, "end": 3}],
        }
        self.base = {"candidate_id": "candidate", "packet_sha256": "packet", "inventory_sha256": "inventory", "reads": []}

    def _read(self, path: str):
        return self.text if path == "docs/a.md" else None

    def _receipt(self, start=1, end=3, **extra):
        raw = "".join(self.text.splitlines(keepends=True)[start - 1 : end]).encode()
        value = {"path": "docs/a.md", "version": "head", "start_line": start, "end_line": end,
                 "sha256": hashlib.sha256(raw).hexdigest(), "assessment": "covers the reviewed requirement", "scope": "FR-1"}
        value.update(extra)
        return value

    def _validate(self, envelope):
        return validate(envelope, candidate_id="candidate", packet_sha256="packet", inventory_sha256="inventory",
                        inventory=self.inventory, read=self._read)

    def test_exact_crlf_range_receipt_closes_required_range(self):
        result = self._validate({**self.base, "reads": [self._receipt()]})
        self.assertTrue(result.complete)
        self.assertEqual(len(result.covered), 1)

    def test_selected_content_without_receipt_is_unread(self):
        result = self._validate(self.base)
        self.assertFalse(result.complete)
        self.assertEqual(result.gaps[0]["code"], "coverage_required_unread")

    def test_wrong_hash_does_not_discard_the_gap(self):
        result = self._validate({**self.base, "reads": [self._receipt(sha256="0" * 64)]})
        self.assertFalse(result.complete)
        self.assertEqual(result.gaps[0]["code"], "coverage_hash_mismatch")
        self.assertTrue(any(g["code"] == "coverage_required_unread" for g in result.gaps))

    def test_partial_and_overlapping_receipts_union_without_overcrediting(self):
        result = self._validate({**self.base, "reads": [self._receipt(1, 2), self._receipt(2, 3), self._receipt(2, 3)]})
        self.assertTrue(result.complete)
        self.assertEqual(len(result.reads), 2)

    def test_missing_assessment_is_invalid_but_other_receipts_remain(self):
        bad = self._receipt(1, 1, assessment="")
        result = self._validate({**self.base, "reads": [bad, self._receipt(2, 3)]})
        self.assertFalse(result.complete)
        self.assertEqual(result.reads[0]["start_line"], 2)
        self.assertEqual(result.gaps[0]["code"], "coverage_read_assessment")

    def test_out_of_bounds_receipt_cannot_claim_coverage_with_an_empty_hash(self):
        result = self._validate({**self.base, "reads": [self._receipt(4, 4, sha256="")]})
        self.assertFalse(result.complete)
        self.assertEqual(result.gaps[0]["code"], "coverage_read_range")

    def test_candidate_mismatch_is_a_gap(self):
        result = self._validate({**self.base, "candidate_id": "other"})
        self.assertEqual(result.gaps[0]["code"], "coverage_candidate_mismatch")

    def test_packet_and_source_version_mismatches_are_uncredited(self):
        packet = self._validate({**self.base, "packet_sha256": "other", "reads": [self._receipt()]})
        version = self._validate({**self.base, "reads": [{**self._receipt(), "version": "old"}]})
        self.assertFalse(packet.reads)
        self.assertFalse(version.reads)
        self.assertEqual(packet.gaps[0]["code"], "coverage_packet_mismatch")
        self.assertEqual(version.gaps[0]["code"], "coverage_source_mismatch")

    def test_escape_and_unavailable_sources_are_uncredited(self):
        escaped = self._validate({**self.base, "reads": [{**self._receipt(), "path": "../secret"}]})
        unavailable = validate({**self.base, "reads": [self._receipt()]}, candidate_id="candidate",
                                packet_sha256="packet", inventory_sha256="inventory", inventory=self.inventory,
                                read=lambda _path: None)
        self.assertEqual(escaped.gaps[0]["code"], "coverage_path_invalid")
        self.assertEqual(unavailable.gaps[0]["code"], "coverage_source_drift")
        self.assertFalse(escaped.reads)
        self.assertFalse(unavailable.reads)

    def test_partial_receipt_reports_only_the_unread_tail(self):
        result = self._validate({**self.base, "reads": [self._receipt(1, 1)]})
        missing = [gap for gap in result.gaps if gap["code"] == "coverage_required_unread"]
        self.assertEqual([(gap["start_line"], gap["end_line"]) for gap in missing], [(2, 3)])

    def test_git_reader_preserves_crlf_bytes_for_receipt_hashes(self):
        repository = TemporaryRepository()
        self.addCleanup(repository.cleanup)
        repository.write("docs/crlf.md", "uno\r\ndos\r\n")
        head = repository.commit("docs/crlf.md", "uno\r\ndos\r\n", "crlf source")
        self.assertEqual(open_git(repository.path).show(head, "docs/crlf.md"), "uno\r\ndos\r\n")


if __name__ == "__main__":
    unittest.main()
