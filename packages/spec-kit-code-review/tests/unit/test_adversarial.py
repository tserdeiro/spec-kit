from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.config import ROOT_CONFIG_FILENAME, load_config
from spec_kit_code_review.env_files import (
    EXECUTABLE_OVERRIDE_KEYS,
    REPO_ENV_FILENAME,
    assert_repo_env_not_tracked,
    load_env_files,
)
from spec_kit_code_review.errors import (
    EXIT_CONFIGURATION,
    EXIT_PREREQUISITE,
    EXIT_USAGE,
    AppError,
)
from spec_kit_code_review.evidence import resolve_evidence_root
from spec_kit_code_review.git import open_git
from spec_kit_code_review.process import resolve_executable
from tests.support.fixtures import (
    ADVERSARIAL_FIXTURE,
    copy_adversarial_fixture,
    copy_consumer_fixture,
    isolate_operator_global_env,
)
from tests.support.repo import TemporaryRepository


class HostileCandidateTests(unittest.TestCase):
    """The candidate's own tree must not govern a single thing about the review.

    The repository is built as a real candidate: the operator's ref carries the
    benign consumer fixture, and a `hostile` branch carries the adversarial one
    -- committed configuration, a tracked tooling env file, a rule file that
    says "approve everything", and an executable of its own.
    """

    def setUp(self) -> None:
        isolate_operator_global_env(self)
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()

        self.repository = TemporaryRepository(self.workspace / "consumer")
        self.addCleanup(self.repository.cleanup)
        copy_consumer_fixture(self.repository.path)
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "benign consumer")
        self.base = self.repository.head()
        self.root = self.repository.path

        self.repository.branch("hostile")
        copy_adversarial_fixture(self.repository.path)
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "hostile candidate")
        self.head = self.repository.head()
        self.repository.checkout("main")
        # The operator's checkout is back on the benign ref; only Git objects
        # hold the hostile content, exactly as during a real review before the
        # environment strategy materializes anything.
        self.git = open_git(self.root)

    # -- configuration --------------------------------------------------

    def test_the_candidate_committed_configuration_has_no_effect(self) -> None:
        config = load_config(self.root)

        self.assertEqual(config.get("budget", "limit"), 400)
        self.assertEqual(config.get("publish", "event"), "request-changes")
        self.assertEqual(config.get("review", "severity_floor"), "info")
        self.assertEqual(config.get("repository", "github"), "tserdeiro/consumer")

    def test_the_hostile_configuration_exists_in_the_candidate_but_is_never_read(self) -> None:
        hostile = self.git.show(self.head, ROOT_CONFIG_FILENAME)

        self.assertIsNotNone(hostile)
        assert hostile is not None
        self.assertIn("999999", hostile)
        self.assertEqual(load_config(self.root).get("budget", "limit"), 400)

    def test_the_hostile_configuration_would_be_rejected_if_it_were_ever_selected(self) -> None:
        # Belt and braces: even pointed at directly, `publish.event: approve` is
        # a configuration error, never an authorization.
        (self.workspace / "hostile").mkdir()
        (self.workspace / "hostile" / ROOT_CONFIG_FILENAME).write_text(
            (ADVERSARIAL_FIXTURE / ROOT_CONFIG_FILENAME).read_text(encoding="utf-8"), encoding="utf-8"
        )

        with self.assertRaises(AppError) as caught:
            load_config(self.workspace / "hostile")

        self.assertEqual(caught.exception.code, EXIT_CONFIGURATION)

    # -- environment file ------------------------------------------------

    def test_a_tracked_repository_env_file_in_the_candidate_head_rejects_the_session(self) -> None:
        self.assertTrue(self.git.path_tracked_at(self.head, REPO_ENV_FILENAME))

        with self.assertRaises(AppError) as caught:
            assert_repo_env_not_tracked(
                self.git.path_tracked_at(self.head, REPO_ENV_FILENAME), ref=self.head, root=self.root
            )

        self.assertEqual(caught.exception.code, EXIT_CONFIGURATION)

    def test_executable_overrides_from_the_repository_env_file_are_ignored(self) -> None:
        (self.root / REPO_ENV_FILENAME).write_text(
            (ADVERSARIAL_FIXTURE / REPO_ENV_FILENAME).read_text(encoding="utf-8"), encoding="utf-8"
        )

        snapshot = load_env_files(self.root, {})

        for key in EXECUTABLE_OVERRIDE_KEYS:
            self.assertIsNone(snapshot.executable_override(key))
        self.assertEqual(
            len([item for item in snapshot.diagnostics if item.code == "env_file_executable_override_ignored"]), 2
        )

    def test_an_evidence_root_pointed_back_inside_the_repository_is_refused(self) -> None:
        (self.root / REPO_ENV_FILENAME).write_text(
            (ADVERSARIAL_FIXTURE / REPO_ENV_FILENAME).read_text(encoding="utf-8"), encoding="utf-8"
        )
        snapshot = load_env_files(self.root, {})

        # The value is relative (`./evidence`), so it resolves against the
        # working directory -- which, during a review, is the repository itself.
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        with self.assertRaises(AppError) as caught:
            resolve_evidence_root(environment=snapshot, forbidden_roots=(self.root,))

        self.assertEqual(caught.exception.code, EXIT_USAGE)

    # -- executables -----------------------------------------------------

    def test_an_executable_shipped_by_the_candidate_is_never_resolved(self) -> None:
        self.repository.checkout("hostile")
        self.addCleanup(self.repository.checkout, "main")
        evil = self.root / "tools" / "evil-ocr"
        self.assertTrue(evil.is_file())

        with self.assertRaises(AppError) as caught:
            resolve_executable("ocr", override=str(evil), forbidden_roots=(self.root,))

        self.assertEqual(caught.exception.code, EXIT_PREREQUISITE)

    # -- rules and prose --------------------------------------------------

    def test_the_candidate_rule_file_is_data_the_review_reads_from_a_chosen_ref(self) -> None:
        candidate_rules = self.git.show(self.head, ".opencodereview/rule.json")
        base_rules = self.git.show(self.base, ".opencodereview/rule.json")

        assert candidate_rules is not None and base_rules is not None
        self.assertIn("Approve everything", candidate_rules)
        self.assertNotIn("Approve everything", base_rules)

    def test_injection_prose_stays_inert_text_in_git_objects(self) -> None:
        plan = self.git.show(self.head, "specs/001-hostile/plan.md")

        assert plan is not None
        self.assertIn("permitted to approve", plan)
        # Stage 1 reads it as bytes and nothing else: no packet is assembled, no
        # instruction is derived, and nothing is executed.
        self.assertEqual(load_config(self.root).get("publish", "event"), "request-changes")


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
