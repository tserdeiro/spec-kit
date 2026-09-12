from types import SimpleNamespace

from spec_kit_code_review.review_context import resolve_scope
from spec_kit_code_review.sdd_context import Artifact, FeatureResolution, SddContext, TaskEntry

def _candidate() -> SimpleNamespace:
    return SimpleNamespace(candidate_id="c" * 64, merge_base="b" * 40, head_commit="h" * 40)
def _task(identifier: str, path: str, block: str | None = None) -> TaskEntry:
    return TaskEntry(identifier, identifier, False, 10, "single", referenced_paths=(path,), block_text=block or identifier)
def _sdd(*entries: TaskEntry, feature: str | None = "007-review-context", source: str = "head-branch", ambiguous: bool = False) -> SddContext:
    resolution = FeatureResolution(
        feature=feature,
        source=source,
        ambiguous=ambiguous,
        candidates=("007-review-context", "008-other") if ambiguous else (),
    )
    empty = Artifact("missing", None, None)
    return SddContext(resolution, empty, empty, task_entries=entries)

def _pr(branch: str) -> SimpleNamespace:
    return SimpleNamespace(head_ref_name=branch)
def test_task_branch_unions_every_changed_task_and_preserves_candidate_identity() -> None:
    scope = resolve_scope(
        _candidate(),
        pull_request=_pr("007-T002-candidate-scope"),
        sdd=_sdd(_task("T001", "src/a.py"), _task("T002", "src/b.py")),
        changed_paths=("src/a.py", "src/b.py"),
    )

    assert scope.kind == "multi-task"
    assert scope.task_ids == ("T001", "T002")
    assert scope.candidate_id == "c" * 64
    assert scope.gaps == ()

def test_feature_branch_covers_the_complete_feature() -> None:
    scope = resolve_scope(
        _candidate(),
        pull_request=_pr("007-review-context"),
        sdd=_sdd(_task("T001", "src/a.py"), _task("T002", "src/b.py")),
        changed_paths=("src/unmatched.py",),
    )

    assert scope.kind == "feature"
    assert scope.task_ids == ("T001", "T002")

def test_task_block_change_is_scope_evidence_even_without_a_path_match() -> None:
    head = _task("T002", "src/b.py", "new block")
    base = _task("T002", "src/b.py", "old block")
    scope = resolve_scope(
        _candidate(),
        pull_request=_pr("007-T002-candidate-scope"),
        sdd=_sdd(head),
        changed_paths=("tasks.md",),
        base_task_entries=(base,),
    )

    assert scope.kind == "task"
    assert scope.task_ids == ("T002",)
    assert scope.gaps == ()
    assert dict(scope.evidence)["changed_task_blocks"] == ["T002"]
def test_issue_key_branch_uses_the_short_path_and_does_not_inherit_a_feature() -> None:
    scope = resolve_scope(
        _candidate(),
        pull_request=_pr("OPS-42-fix-timeout"),
        sdd=_sdd(feature=None, source="none"),
        changed_paths=("src/timeout.py",),
    )

    assert scope.kind == "short-path"
    assert scope.task_ids == ()
    assert scope.gaps == ()
def test_ambiguous_feature_is_an_immediate_scope_gap() -> None:
    scope = resolve_scope(
        _candidate(),
        pull_request=_pr("007-review-context"),
        sdd=_sdd(_task("T001", "src/a.py"), ambiguous=True),
        changed_paths=("src/a.py",),
    )

    assert scope.unresolved
    assert any(gap.code == "feature_ambiguous" for gap in scope.gaps)

def test_explicit_refs_cover_the_resolved_feature() -> None:
    scope = resolve_scope(_candidate(), pull_request=None, sdd=_sdd(_task("T001", "src/a.py"), _task("T002", "src/b.py"), source="feature.json"), changed_paths=("src/a.py",))
    assert scope.kind == "feature"
    assert scope.task_ids == ("T001", "T002")

def test_deleted_task_block_keeps_feature_scope_and_gap() -> None:
    scope = resolve_scope(_candidate(), pull_request=_pr("007-T002-candidate-scope"), sdd=_sdd(), changed_paths=("tasks.md",), base_task_entries=(_task("T003", "src/c.py", "deleted"),))
    assert scope.kind == "feature" and "T003" in scope.task_ids
    assert any(gap.code == "task_block_missing" for gap in scope.gaps)
