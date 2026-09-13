from types import SimpleNamespace

from spec_kit_code_review.review_context import resolve_scope, select_context
from spec_kit_code_review.sdd_context import Artifact, FeatureResolution, SddContext, TaskEntry, parse_tasks

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

def test_native_work_item_resolution_wins_over_stale_feature_selection() -> None:
    resolution = FeatureResolution(feature="007-review-context", source="feature.json", work_item_key="OPS-42")
    empty = Artifact("missing", None, None)
    sdd = SddContext(resolution, empty, empty, task_entries=(_task("T001", "src/a.py"),))
    scope = resolve_scope(_candidate(), pull_request=_pr("users/alice/fix-timeout"), sdd=sdd, changed_paths=("src/timeout.py",))

    assert scope.kind == "short-path"
    assert scope.feature is None
    assert scope.task_ids == ()
    assert scope.gaps == ()

def test_unsupported_native_title_is_explicit_advisory_and_drops_stale_feature() -> None:
    scope = resolve_scope(
        _candidate(),
        pull_request=_pr("users/alice/fix-timeout"),
        sdd=_sdd(_task("T001", "src/a.py"), source="feature.json"),
        changed_paths=("src/timeout.py",),
    )

    assert scope.kind == "short-path"
    assert scope.feature is None
    assert any(gap.code == "branch_unrecognized" for gap in scope.gaps)

def test_nested_native_task_like_leaf_does_not_get_task_scope() -> None:
    scope = resolve_scope(
        _candidate(),
        pull_request=_pr("users/alice/001-T001-change"),
        sdd=_sdd(_task("T001", "src/a.py"), source="head-branch"),
        changed_paths=("src/a.py",),
    )

    assert scope.kind == "short-path"
    assert scope.task_ids == ()
    assert scope.feature is None
    assert any(gap.code == "branch_unrecognized" for gap in scope.gaps)

def test_conflicting_work_item_identity_is_an_unresolved_scope() -> None:
    resolution = FeatureResolution(
        source="work-item",
        candidates=("OPS-42", "OPS-43"),
        work_item_candidates=("OPS-42", "OPS-43"),
        ambiguous=True,
        identity_conflict=True,
    )
    empty = Artifact("missing", None, None)
    scope = resolve_scope(
        _candidate(),
        pull_request=_pr("users/alice/fix-timeout"),
        sdd=SddContext(resolution, empty, empty),
        changed_paths=("src/timeout.py",),
    )

    assert scope.kind == "short-path"
    assert any(gap.code == "work_item_identity_conflict" for gap in scope.gaps)
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

def test_selection_keeps_late_task_and_ledger_strategy_but_excludes_unrelated_blocks() -> None:
    first = TaskEntry("T001", "old", False, 1, "single", referenced_paths=("src/old.py",), source_start=3, source_end=3, block_text="old block")
    late = TaskEntry("T002", "late", False, 1, "single", referenced_paths=("src/new.py",), source_start=4, source_end=4, block_text="late block")
    tasks = Artifact("specs/007/tasks.md", "Delivery strategy\n\n" + first.block_text + "\n" + late.block_text + "\n", "x")
    sdd = SddContext(FeatureResolution(feature="007-review-context"), Artifact("constitution", None), Artifact("feature", None), tasks=tasks, task_entries=(first, late))
    scope = resolve_scope(_candidate(), pull_request=_pr("007-T002-work"), sdd=sdd, changed_paths=("src/new.py",), base_task_entries=(first, late))
    selection = select_context(sdd, scope)
    assert any("task ledger shared prose" in item.reason for item in selection.selected)
    assert any(item.start == first.source_start and item.reason == "outside selected scope" for item in selection.excluded)
    assert any(item.start == late.source_start for item in selection.selected)

def test_selection_includes_direct_dependency_and_reports_cycles() -> None:
    first = TaskEntry("T001", "one", False, 1, "single", dependencies=("T002",), source_start=2, source_end=2, block_text="one")
    second = TaskEntry("T002", "two", True, 1, "single", dependencies=("T001",), source_start=3, source_end=3, block_text="two")
    tasks = Artifact("tasks.md", "header\none\ntwo\n", "x")
    sdd = SddContext(FeatureResolution(feature="007-review-context"), Artifact("constitution", None), Artifact("feature", None), tasks=tasks, task_entries=(first, second))
    scope = resolve_scope(_candidate(), pull_request=_pr("007-T001-work"), sdd=sdd, changed_paths=("src/new.py",), base_task_entries=(first, second))
    selection = select_context(sdd, scope)
    assert any(item.start <= 2 and item.end >= 3 for item in selection.selected)
    assert any(gap.code == "dependency_cycle" for gap in selection.gaps)

def test_selection_reports_missing_requirement_reference() -> None:
    entry = TaskEntry("T001", "one", False, 1, "single", referenced_paths=("src/new.py",), traces=("FR-999",), source_start=1, source_end=1, block_text="one")
    spec = Artifact("spec.md", "# Spec\n\n## Requirements\n\n- FR-001: present\n", "x")
    sdd = SddContext(FeatureResolution(feature="007-review-context"), Artifact("constitution", None), Artifact("feature", None), spec=spec, task_entries=(entry,))
    scope = resolve_scope(_candidate(), pull_request=_pr("007-T001-work"), sdd=sdd, changed_paths=("src/new.py",))
    selection = select_context(sdd, scope)
    assert any(gap.code == "requirement_missing" for gap in selection.gaps)

def test_feature_scope_reports_missing_contract_artifacts_before_selection() -> None:
    entry = TaskEntry("T001", "one", False, 1, "single", referenced_paths=("src/new.py",), source_start=1, source_end=1, block_text="one")
    plan = Artifact("plan.md", "# Plan\ncontract\n", "x")
    tasks = Artifact("tasks.md", "# Tasks\none\n", "x")
    sdd = SddContext(FeatureResolution(feature="007-review-context"), Artifact("constitution", None), Artifact("feature", None), plan=plan, tasks=tasks, task_entries=(entry,))
    scope = resolve_scope(_candidate(), pull_request=_pr("007-review-context"), sdd=sdd, changed_paths=("src/new.py",))
    selection = select_context(sdd, scope)
    missing = [gap for gap in selection.gaps if gap.code == "required_artifact_missing"]
    assert any(gap.affected == ("spec", "specs/007-review-context/spec.md") for gap in missing)

def test_feature_scope_reports_empty_spec_and_plan_contracts() -> None:
    sdd = SddContext(
        FeatureResolution(feature="007-review-context"),
        Artifact("constitution", None),
        Artifact("feature", None),
        spec=Artifact("spec.md", "  \n", "x"),
        plan=Artifact("plan.md", "", "x"),
    )
    scope = resolve_scope(_candidate(), pull_request=_pr("007-review-context"), sdd=sdd, changed_paths=())
    selection = select_context(sdd, scope)
    missing = [gap.affected[0] for gap in selection.gaps if gap.code == "required_artifact_missing"]
    assert missing == ["spec", "plan"]

def test_feature_review_before_task_generation_does_not_require_ledger() -> None:
    sdd = SddContext(
        FeatureResolution(feature="007-review-context"),
        Artifact("constitution", None),
        Artifact("feature", None),
        spec=Artifact("spec.md", "# Spec\n## FR-001\ncontract\n", "x"),
        plan=Artifact("plan.md", "# Plan\nplanning\n", "x"),
    )
    scope = resolve_scope(_candidate(), pull_request=_pr("007-review-context"), sdd=sdd, changed_paths=())
    selection = select_context(sdd, scope)
    assert not any(gap.code == "required_artifact_missing" for gap in selection.gaps)

def test_short_path_does_not_require_feature_contract_artifacts() -> None:
    sdd = _sdd(feature=None, source="none")
    scope = resolve_scope(_candidate(), pull_request=_pr("OPS-42-fix-timeout"), sdd=sdd, changed_paths=("src/timeout.py",))
    selection = select_context(sdd, scope)
    assert not any(gap.code == "required_artifact_missing" for gap in selection.gaps)

def test_selection_finds_task_after_sixty_thousand_bytes_of_unrelated_ledger() -> None:
    prefix = ("Earlier phase prose that is unrelated to this candidate.\n" * 1400)
    text = prefix + "- [ ] T099 Late task\n  - **Boundaries**: Change src/late.py.\n"
    entries = parse_tasks(text)
    late = entries[0]
    tasks = Artifact("specs/007/tasks.md", text, "x")
    sdd = SddContext(FeatureResolution(feature="007-review-context"), Artifact("constitution", None), Artifact("feature", None), tasks=tasks, task_entries=entries)
    scope = resolve_scope(_candidate(), pull_request=_pr("007-T099-work"), sdd=sdd, changed_paths=("src/late.py",), base_task_entries=entries)
    selection = select_context(sdd, scope)
    assert len(text.encode("utf-8")) > 60000
    assert any(item.start <= late.source_start and item.end >= late.source_end for item in selection.selected)
    assert any(item.start == 1 and item.end >= late.source_end for item in selection.selected)

def test_selection_excludes_unrelated_explicit_requirement_but_keeps_unscoped_section() -> None:
    entry = TaskEntry("T001", "one", False, 1, "single", referenced_paths=("src/a.py",), traces=("FR-001",), source_start=2, source_end=2, block_text="one")
    spec = Artifact("spec.md", "# Spec\n## FR-001\nneeded\n## FR-999\nunrelated\n## Shared constraints\nkeep this and preserve FR-999 when applicable\n", "x")
    tasks = Artifact("tasks.md", "header\none\n", "x")
    sdd = SddContext(FeatureResolution(feature="007-review-context"), Artifact("constitution", None), Artifact("feature", None), spec=spec, tasks=tasks, task_entries=(entry,))
    scope = resolve_scope(_candidate(), pull_request=_pr("007-T001-work"), sdd=sdd, changed_paths=("src/a.py",), base_task_entries=(entry,))
    selection = select_context(sdd, scope)
    spec_selected = [item for item in selection.selected if item.path == "spec.md"]
    assert any(item.start <= 2 and item.end >= 3 for item in spec_selected)
    assert any(item.start == 6 and item.end == 7 for item in spec_selected)
    assert any(item.start == 4 and item.end == 5 for item in selection.excluded)

def test_shared_headings_and_preamble_retain_incidental_requirement_references() -> None:
    entry = TaskEntry("T001", "one", False, 1, "single", referenced_paths=("src/a.py",), traces=("FR-001",), source_start=1, source_end=1, block_text="one")
    spec = Artifact(
        "spec.md",
        "preamble policy FR-999\n## FR-001\nneeded\n## Shared constraints for FR-999\nkeep global policy\n## FR-999\nunrelated\n",
        "x",
    )
    sdd = SddContext(FeatureResolution(feature="007-review-context"), Artifact("constitution", None), Artifact("feature", None), spec=spec, task_entries=(entry,))
    scope = resolve_scope(_candidate(), pull_request=_pr("007-T001-work"), sdd=sdd, changed_paths=("src/a.py",), base_task_entries=(entry,))
    selection = select_context(sdd, scope)
    assert any(item.path == "spec.md" and item.start == 1 and item.end >= 5 for item in selection.selected)
    assert any(item.path == "spec.md" and item.start == 6 and item.end == 7 for item in selection.excluded)

def test_selection_keeps_parent_intro_before_a_requirement_heading() -> None:
    entry = TaskEntry("T001", "one", False, 1, "single", referenced_paths=("src/a.py",), traces=("FR-001",), source_start=1, source_end=1, block_text="one")
    spec = Artifact("spec.md", "# Spec\nparent policy\n## FR-001\nneeded\n", "x")
    sdd = SddContext(FeatureResolution(feature="007-review-context"), Artifact("constitution", None), Artifact("feature", None), spec=spec, task_entries=(entry,))
    scope = resolve_scope(_candidate(), pull_request=_pr("007-T001-work"), sdd=sdd, changed_paths=("src/a.py",), base_task_entries=(entry,))
    selection = select_context(sdd, scope)
    assert any(item.path == "spec.md" and item.start == 1 and item.end >= 3 for item in selection.selected)

def test_feature_scope_keeps_untraced_spec_contract_and_plan_has_no_requirement_gap() -> None:
    entry = TaskEntry("T001", "one", False, 1, "single", traces=("FR-001",), source_start=1, source_end=1, block_text="one")
    spec = Artifact("spec.md", "# Spec\n## FR-001\nneeded\n## FR-999\nuntraced\n", "x")
    plan = Artifact("plan.md", "# Plan\n## Delivery\nno identifiers\n", "x")
    sdd = SddContext(FeatureResolution(feature="007-review-context"), Artifact("constitution", None), Artifact("feature", None), spec=spec, plan=plan, task_entries=(entry,), requirement_ids=("FR-001",))
    scope = resolve_scope(_candidate(), pull_request=_pr("007-review-context"), sdd=sdd, changed_paths=("src/a.py",), base_task_entries=(entry,))
    selection = select_context(sdd, scope)
    assert any(item.path == "spec.md" and item.start == 1 and item.end == 5 for item in selection.selected)
    assert not any(gap.code == "requirement_missing" and "plan.md" in gap.affected for gap in selection.gaps)

def test_long_dependency_chain_is_checked_without_recursive_depth_failure() -> None:
    entries = tuple(TaskEntry(f"T{i:04d}", "task", False, 1, "single", dependencies=(f"T{i + 1:04d}",) if i < 1100 else (), source_start=i + 1, source_end=i + 1, block_text="task") for i in range(1, 1101))
    sdd = SddContext(FeatureResolution(feature="007-review-context"), Artifact("constitution", None), Artifact("feature", None), tasks=Artifact("tasks.md", "\n".join("task" for _ in entries), "x"), task_entries=entries)
    scope = resolve_scope(_candidate(), pull_request=_pr("007-review-context"), sdd=sdd, changed_paths=(), base_task_entries=entries)
    selection = select_context(sdd, scope)
    assert not any(gap.code == "dependency_cycle" for gap in selection.gaps)
