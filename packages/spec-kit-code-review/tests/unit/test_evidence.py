from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.config import load_config
from spec_kit_code_review.env_files import EnvSnapshot
from spec_kit_code_review.errors import EXIT_USAGE, AppError
from spec_kit_code_review.evidence import (
    DIRECTORY_MODE,
    enforce_permissions,
    permission_diagnostics,
    repository_id,
    resolve_evidence_root,
)
from spec_kit_code_review.session import inventory
from tests.support.fixtures import isolate_operator_global_env


def _snapshot(**values: str) -> EnvSnapshot:
    return EnvSnapshot(values=dict(values), trusted=dict(values))


class EvidenceRootResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        isolate_operator_global_env(self)
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.repository = self.workspace / "repository"
        self.repository.mkdir()

    def test_environment_beats_configuration(self) -> None:
        (self.repository / "speckit-code-review.yml").write_text('schema_version: "1.0"\n', encoding="utf-8")
        (self.repository / "speckit-code-review.local.yml").write_text(
            f'evidence:\n  root: "{self.workspace / "from-config"}"\n', encoding="utf-8"
        )
        config = load_config(self.repository)
        environment = _snapshot(SPECKIT_CODE_REVIEW_EVIDENCE_DIR=str(self.workspace / "from-environment"))

        self.assertEqual(
            resolve_evidence_root(environment=environment, config=config).path,
            self.workspace / "from-environment",
        )
        self.assertEqual(resolve_evidence_root(config=config).path, self.workspace / "from-config")

    def test_default_uses_the_state_directory_of_the_distribution_namespace(self) -> None:
        resolved = resolve_evidence_root()

        # Doc "Rutas por usuario": <state>/tserdeiro/spec-kit/code-review.
        self.assertEqual(resolved.path.name, "code-review")
        self.assertEqual(resolved.path.parent.name, "spec-kit")
        self.assertEqual(resolved.path.parent.parent.name, "tserdeiro")
        self.assertIn(resolved.source, {"xdg", "home"})

    def test_the_state_variable_is_honoured(self) -> None:
        from unittest import mock

        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.workspace / "state")}, clear=False):
            resolved = resolve_evidence_root()

        self.assertEqual(resolved.path, self.workspace / "state" / "tserdeiro" / "spec-kit" / "code-review")
        self.assertEqual(resolved.source, "xdg")

    def test_a_root_inside_the_repository_is_rejected_from_either_source(self) -> None:
        inside = self.repository / ".specify" / "review"
        (self.repository / "speckit-code-review.yml").write_text('schema_version: "1.0"\n', encoding="utf-8")
        (self.repository / "speckit-code-review.local.yml").write_text(
            f'evidence:\n  root: "{inside}"\n', encoding="utf-8"
        )
        config = load_config(self.repository)

        cases = {
            "environment": dict(environment=_snapshot(SPECKIT_CODE_REVIEW_EVIDENCE_DIR=str(inside))),
            "configuration": dict(config=config),
        }
        for source, keywords in cases.items():
            with self.subTest(source=source):
                with self.assertRaises(AppError) as caught:
                    resolve_evidence_root(forbidden_roots=(self.repository,), **keywords)
                self.assertEqual(caught.exception.code, EXIT_USAGE)
                self.assertIn(source, caught.exception.diagnostics[0].message)

    def test_the_repository_toplevel_itself_is_rejected(self) -> None:
        with self.assertRaises(AppError) as caught:
            resolve_evidence_root(
                environment=_snapshot(SPECKIT_CODE_REVIEW_EVIDENCE_DIR=str(self.repository)),
                forbidden_roots=(self.repository,),
            )

        self.assertEqual(caught.exception.code, EXIT_USAGE)

    def test_a_temporary_worktree_is_rejected_too(self) -> None:
        worktree = self.workspace / "worktree"
        worktree.mkdir()

        with self.assertRaises(AppError) as caught:
            resolve_evidence_root(
                environment=_snapshot(SPECKIT_CODE_REVIEW_EVIDENCE_DIR=str(worktree / "evidence")),
                forbidden_roots=(self.repository, worktree),
            )

        self.assertEqual(caught.exception.code, EXIT_USAGE)

    def test_a_sibling_directory_is_accepted(self) -> None:
        outside = self.workspace / "evidence"

        resolved = resolve_evidence_root(
            environment=_snapshot(SPECKIT_CODE_REVIEW_EVIDENCE_DIR=str(outside)),
            forbidden_roots=(self.repository,),
        )

        self.assertEqual(resolved.path, outside)
        self.assertEqual(resolved.source, "environment")


class EvidenceInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()

    def _session(self, head: str, phase: str) -> None:
        directory = self.workspace / "evidence" / "owner-name" / head
        directory.mkdir(parents=True)
        (directory / "session.json").write_text(
            json.dumps({"phase": phase, "candidate_id": f"cid-{head}", "head_commit": head}), encoding="utf-8"
        )

    def test_only_open_sessions_are_inventoried(self) -> None:
        self._session("a" * 40, "open")
        self._session("b" * 40, "closed")
        (self.workspace / "evidence" / "owner-name" / ("c" * 40)).mkdir(parents=True)
        (self.workspace / "evidence" / "owner-name" / ("c" * 40) / "session.json").write_text("{not json", encoding="utf-8")

        root = resolve_evidence_root(
            environment=_snapshot(SPECKIT_CODE_REVIEW_EVIDENCE_DIR=str(self.workspace / "evidence"))
        )
        sessions = inventory(root)

        self.assertEqual([session.candidate_id for session in sessions], [f"cid-{'a' * 40}"])

    def test_permissions_are_reported_and_fixable(self) -> None:
        root = self.workspace / "evidence"
        root.mkdir()
        root.chmod(0o755)
        resolved = resolve_evidence_root(environment=_snapshot(SPECKIT_CODE_REVIEW_EVIDENCE_DIR=str(root)))

        codes = [diagnostic.code for diagnostic in permission_diagnostics(resolved)]
        self.assertIn("evidence_root_permissions", codes)

        self.assertTrue(enforce_permissions(resolved))
        self.assertEqual(resolved.mode, DIRECTORY_MODE)
        self.assertFalse(enforce_permissions(resolved))

    def test_repository_id_is_stable_and_falls_back_to_the_path(self) -> None:
        self.assertEqual(repository_id("tserdeiro/Spec-Kit", self.workspace), "tserdeiro-spec-kit")
        self.assertEqual(repository_id(None, self.workspace), repository_id(None, self.workspace))
        self.assertTrue(repository_id(None, self.workspace).startswith("path-"))


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
