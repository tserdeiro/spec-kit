from __future__ import annotations

import json
import os
import stat
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.env_files import EnvSnapshot
from spec_kit_code_review.errors import EXIT_DRIFT, EXIT_USAGE, AppError
from spec_kit_code_review.evidence import FILE_MODE, resolve_evidence_root
from spec_kit_code_review.session import (
    PHASE_ABANDONED,
    PHASE_CLOSED,
    PHASE_OPEN,
    apply_retention,
    detect_drift,
    inventory,
    load_session,
    open_session,
    require_open,
    session_directory,
)


def _evidence_env(path) -> EnvSnapshot:
    values = {"SPECKIT_CODE_REVIEW_EVIDENCE_DIR": str(path)}
    return EnvSnapshot(values=values, trusted=dict(values))


CANDIDATE = {
    "candidate_id": "c" * 64,
    "head_commit": "a" * 40,
    "merge_base": "b" * 40,
    "repository": "tserdeiro/consumer",
    "pr_number": 128,
}
ENVIRONMENT = {
    "head_commit": "a" * 40,
    "repository_root": "/tmp/consumer",
    "working_root": "/tmp/evidence/worktree",
    "worktree_path": "/tmp/evidence/worktree",
    "forbidden_roots": ["/tmp/consumer"],
}


class SessionCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.evidence = resolve_evidence_root(environment=_evidence_env(self.workspace / "evidence"))

    def _open(self, head: str = CANDIDATE["head_commit"], **candidate_overrides):
        candidate = {**CANDIDATE, "head_commit": head, **candidate_overrides}
        directory = session_directory(self.evidence, "tserdeiro-consumer", head)
        return open_session(directory=directory, candidate=candidate, environment=ENVIRONMENT, config_sha256="deadbeef")


class SessionDocumentTests(SessionCase):
    def test_the_layout_is_the_documented_one(self) -> None:
        session = self._open()

        self.assertEqual(session.path.parent.name, "tserdeiro-consumer")
        self.assertEqual(session.path.name, CANDIDATE["head_commit"])
        self.assertTrue(session.document.is_file())
        self.assertTrue((session.path / "env" / "environment.json").is_file())

    def test_the_session_records_everything_needed_to_restore_the_environment(self) -> None:
        session = self._open()
        payload = json.loads(session.document.read_text(encoding="utf-8"))

        self.assertEqual(payload["phase"], PHASE_OPEN)
        self.assertEqual(payload["candidate_id"], CANDIDATE["candidate_id"])
        self.assertEqual(payload["merge_base"], CANDIDATE["merge_base"])
        self.assertEqual(payload["working_root"], "/tmp/evidence/worktree")
        self.assertEqual(payload["environment"]["worktree_path"], "/tmp/evidence/worktree")
        self.assertEqual(payload["config_sha256"], "deadbeef")
        self.assertIsNone(payload["packet_sha256"])

    def test_evidence_documents_are_not_world_readable(self) -> None:
        session = self._open()

        self.assertEqual(stat.S_IMODE(session.document.stat().st_mode), FILE_MODE)

    def test_the_summary_names_the_candidate_and_its_worktree(self) -> None:
        session = self._open()

        summary = session.summary()

        self.assertEqual(summary["candidate_id"], CANDIDATE["candidate_id"])
        self.assertEqual(summary["worktree_path"], "/tmp/evidence/worktree")
        self.assertIsNotNone(summary["age_hours"])

    def test_the_age_is_computed_from_the_opening_timestamp(self) -> None:
        session = self._open()
        session.payload["opened_at"] = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat().replace("+00:00", "Z")

        self.assertAlmostEqual(session.age_hours(), 30.0, delta=0.2)

    def test_marking_a_session_rewrites_its_phase(self) -> None:
        session = self._open()

        session.mark(PHASE_ABANDONED, environment_restored=True)

        self.assertEqual(load_session(session.path).phase, PHASE_ABANDONED)
        self.assertIsNotNone(load_session(session.path).payload["closed_at"])

    def test_an_unknown_phase_is_a_programming_error(self) -> None:
        session = self._open()

        with self.assertRaises(ValueError):
            session.mark("finished")


class SessionLoadingTests(SessionCase):
    def test_a_missing_session_is_a_usage_error(self) -> None:
        with self.assertRaises(AppError) as caught:
            load_session(self.workspace / "nowhere")

        self.assertEqual(caught.exception.code, EXIT_USAGE)
        self.assertEqual(caught.exception.diagnostics[0].code, "session_missing")

    def test_a_malformed_session_is_a_usage_error(self) -> None:
        directory = self.workspace / "broken"
        directory.mkdir()
        (directory / "session.json").write_text("{not json", encoding="utf-8")

        with self.assertRaises(AppError) as caught:
            load_session(directory)

        self.assertEqual(caught.exception.code, EXIT_USAGE)

    def test_the_document_path_is_accepted_as_well_as_its_directory(self) -> None:
        session = self._open()

        self.assertEqual(load_session(session.document).path, session.path)

    def test_a_closed_session_cannot_be_closed_again(self) -> None:
        session = self._open()
        session.mark(PHASE_CLOSED, verdict="no-blocking-findings")

        with self.assertRaises(AppError) as caught:
            require_open(load_session(session.path))

        self.assertEqual(caught.exception.code, EXIT_USAGE)
        self.assertIn("no-blocking-findings", caught.exception.diagnostics[0].message)

    def test_an_open_session_passes_the_gate(self) -> None:
        session = self._open()

        self.assertIs(require_open(session), session)


class InventoryTests(SessionCase):
    def test_only_open_sessions_are_inventoried_by_default(self) -> None:
        first = self._open(head="a" * 40)
        second = self._open(head="b" * 40)
        second.mark(PHASE_CLOSED)

        self.assertEqual([session.path for session in inventory(self.evidence)], [first.path])
        self.assertEqual(len(inventory(self.evidence, phase=None)), 2)

    def test_a_malformed_document_is_skipped_never_a_crash(self) -> None:
        self._open()
        broken = self.evidence.path / "tserdeiro-consumer" / ("d" * 40)
        broken.mkdir(parents=True)
        (broken / "session.json").write_text("{not json", encoding="utf-8")

        self.assertEqual(len(inventory(self.evidence)), 1)

    def test_an_absent_evidence_root_is_an_empty_inventory(self) -> None:
        self.assertEqual(inventory(resolve_evidence_root(environment=_evidence_env(self.workspace / "absent"))), [])


class RetentionTests(SessionCase):
    def _closed(self, head: str, *, age_seconds: float) -> Path:
        session = self._open(head=head)
        session.mark(PHASE_CLOSED)
        stamp = datetime.now(timezone.utc).timestamp() - age_seconds
        os.utime(session.document, (stamp, stamp))
        return session.path

    def test_the_oldest_closed_sessions_are_removed(self) -> None:
        oldest = self._closed("1" * 40, age_seconds=400)
        middle = self._closed("2" * 40, age_seconds=300)
        newest = self._closed("3" * 40, age_seconds=100)

        removed = apply_retention(self.evidence, "tserdeiro-consumer", keep=2)

        self.assertEqual(removed, [oldest])
        self.assertFalse(oldest.exists())
        self.assertTrue(middle.exists())
        self.assertTrue(newest.exists())

    def test_an_open_session_never_falls_to_retention(self) -> None:
        # Deleting it would leave an unrestored environment with no record of how
        # to restore it.
        open_session_path = self._open(head="9" * 40).path
        stamp = datetime.now(timezone.utc).timestamp() - 10_000
        os.utime(open_session_path / "session.json", (stamp, stamp))
        for index in range(3):
            self._closed(f"{index}" * 40, age_seconds=100 + index)

        apply_retention(self.evidence, "tserdeiro-consumer", keep=1)

        self.assertTrue(open_session_path.exists())
        self.assertEqual(load_session(open_session_path).phase, PHASE_OPEN)

    def test_the_session_about_to_be_opened_is_protected(self) -> None:
        protected = self._closed("5" * 40, age_seconds=5_000)

        apply_retention(self.evidence, "tserdeiro-consumer", keep=0, protect=protected)

        self.assertTrue(protected.exists())

    def test_nothing_is_removed_below_the_threshold(self) -> None:
        self._closed("1" * 40, age_seconds=400)

        self.assertEqual(apply_retention(self.evidence, "tserdeiro-consumer", keep=20), [])


class DriftTests(unittest.TestCase):
    def test_a_moved_head_is_drift(self) -> None:
        drift = detect_drift(
            previous_head="a" * 40,
            previous_merge_base="b" * 40,
            current_head="c" * 40,
            current_merge_base="b" * 40,
        )

        self.assertIsNotNone(drift)
        self.assertEqual(drift.kind, "head")
        self.assertEqual(drift.as_error().code, EXIT_DRIFT)
        self.assertIn("new commits to review", drift.diagnostic.message)

    def test_a_moved_merge_base_with_the_same_head_is_also_drift(self) -> None:
        drift = detect_drift(
            previous_head="a" * 40,
            previous_merge_base="b" * 40,
            current_head="a" * 40,
            current_merge_base="d" * 40,
        )

        self.assertIsNotNone(drift)
        self.assertEqual(drift.kind, "merge_base")
        self.assertEqual(drift.as_error().code, EXIT_DRIFT)
        # The operator's action differs, so the message must distinguish the case.
        self.assertIn("the head did not move", drift.diagnostic.message)
        self.assertIn("redo the pass against the new range", drift.diagnostic.message)

    def test_an_unchanged_candidate_is_not_drift(self) -> None:
        self.assertIsNone(
            detect_drift(
                previous_head="a" * 40,
                previous_merge_base="b" * 40,
                current_head="a" * 40,
                current_merge_base="b" * 40,
            )
        )

    def test_an_unknown_side_is_never_reported_as_drift(self) -> None:
        self.assertIsNone(
            detect_drift(previous_head=None, previous_merge_base=None, current_head="a" * 40, current_merge_base="b" * 40)
        )


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
