"""The compact documents are derived from the full ones, never assembled twice."""

from __future__ import annotations

import unittest

from spec_kit_code_review.reporting import compact_close, compact_open


def _open_payload(session_path: str) -> dict:
    return {
        "code": 0, "category": "ok", "message": "review packet ready",
        "candidate": {"candidate_id": "c", "head_commit": "h", "merge_base": "m", "base_branch": "main", "pr_number": 7, "repository": "o/r"},
        "session": {"path": session_path, "phase": "open", "opened_at": "2026-09-13T00:00:00Z"},
        "packet": {"packet_sha256": "p", "inventory_sha256": "i", "bytes": 10, "truncations": [{"path": "x"}]},
        "budget": {"counted": 1, "limit": 400, "over_budget": False},
        "scope": {"files": [{"path": "a"}, {"path": "b"}], "included_count": 1},
        "diagnostics": [{"code": "x", "message": "m", "severity": "info"}, {"code": "y", "message": "n", "severity": "warning"}],
    }


class CompactOpenTests(unittest.TestCase):
    def test_paths_come_from_the_session_and_are_quoted_for_the_shell(self) -> None:
        document = compact_open(_open_payload("/tmp/ev/a b"), extension_version="0.6.0")

        self.assertEqual(document["packet"]["path"], "/tmp/ev/a b/review-packet.md")
        self.assertEqual(document["packet"]["inventory_path"], "/tmp/ev/a b/context-inventory.json")
        self.assertEqual(document["packet"]["truncations"], 1)
        self.assertEqual(document["scope"], {"included_count": 1})
        self.assertEqual(document["next"]["findings_path"], "/tmp/ev/a b/findings.json")
        self.assertEqual(document["next"]["close"], "review --findings '/tmp/ev/a b/findings.json' --session '/tmp/ev/a b'")
        self.assertEqual([item["code"] for item in document["warnings"]], ["y"])
        self.assertEqual(document["runtime"], {"extension_version": "0.6.0"})


class CompactCloseTests(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "code": 1, "category": "findings", "message": "changes-requested",
            "candidate": {"candidate_id": "c", "head_commit": "h", "merge_base": "m", "base_branch": "main", "pr_number": 7, "repository": "o/r"},
            "session": {"path": "/tmp/ev/s", "phase": "closed"},
            "verdict": {"value": "changes-requested", "blocking": 1, "causes": []},
            "delivery": {"decision": "hold", "reason": "blocking", "pending": ["F001"], "counts": {"blocking": 1}, "is_approval": False},
            "coverage": {"complete": True, "uncovered": []},
            "findings": [{"identifier": "F001"}], "discarded_findings": [],
            "diagnostics": [],
        }

    def test_a_close_without_publication_carries_no_publication_keys(self) -> None:
        document = compact_close(self._payload())

        self.assertNotIn("publication", document)
        self.assertNotIn("operations", document)
        self.assertEqual(document["findings"]["path"], "/tmp/ev/s/findings.md")

    def test_a_published_close_keeps_what_the_publication_did(self) -> None:
        payload = self._payload()
        payload["publication"] = {"executed": True, "event": "REQUEST_CHANGES", "posted_inline": 1, "review_urls": ["u"], "summary_comment_url": "s", "summary_marker": "hidden"}
        payload["operations"] = [{"kind": "review"}, {"kind": "comment"}]

        document = compact_close(payload)

        self.assertEqual(document["publication"], {"executed": True, "event": "REQUEST_CHANGES", "posted_inline": 1, "review_urls": ["u"], "summary_comment_url": "s"})
        self.assertEqual(document["operations"], 2)


if __name__ == "__main__":
    unittest.main()
