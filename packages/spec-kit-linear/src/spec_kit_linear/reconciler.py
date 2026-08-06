"""Fail-closed application of a rendered remote plan."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .errors import AppError, Diagnostic
from .planner import operation_precondition_holds, snapshot_is_current


class ApplyTransport(Protocol):
    """Small testable boundary; implementations may use stdlib GraphQL only."""

    def execute(self, operation: Mapping[str, object]) -> Mapping[str, object]: ...


SnapshotProvider = Callable[[], Mapping[str, object]]
PostVerifier = Callable[[Mapping[str, object]], bool]


@dataclass(frozen=True)
class ApplyResult:
    applied_operation_ids: tuple[str, ...]
    recovered_operation_ids: tuple[str, ...]
    writes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "applied_operation_ids": list(self.applied_operation_ids),
            "recovered_operation_ids": list(self.recovered_operation_ids),
            "writes": self.writes,
        }


def apply_plan(
    plan: Mapping[str, object],
    *,
    snapshot_provider: SnapshotProvider,
    transport: ApplyTransport,
    post_verify: PostVerifier | None = None,
) -> ApplyResult:
    """Apply exactly ``plan``, checking a fresh snapshot before every write.

    A network timeout after a mutation is not retried.  The target identity is
    queried first; if the expected creation materialized, it is recovered and
    execution moves on.  Otherwise the original ambiguity is surfaced.
    """

    expected_snapshot = _mapping(plan.get("snapshot"), "plan_snapshot")
    initial = snapshot_provider()
    if not snapshot_is_current(expected_snapshot, initial):
        raise _apply_error("snapshot_stale", "remote snapshot changed while planning; run push again")
    operations = _operations(plan)
    resolved_ids = _snapshot_ids(initial)
    created: set[str] = set()
    changed: set[str] = set()
    applied: list[str] = []
    recovered: list[str] = []

    for operation in operations:
        current = snapshot_provider()
        # Existing resources from the rendered snapshot must be unchanged;
        # resources made by prior operations are intentionally excluded from
        # that immutable baseline and checked separately below.
        if not snapshot_is_current(expected_snapshot, current, ignored_identities=frozenset(changed)):
            raise _apply_error("snapshot_stale", "remote snapshot changed before the next mutation")
        current_ids = _snapshot_ids(current)
        for identity in created:
            expected_id = resolved_ids.get(identity)
            if expected_id is None or current_ids.get(identity) != expected_id:
                raise _apply_error("create_not_visible", "a previous create was not visible during mandatory revalidation")
        target = str(operation["target"])
        if target in changed:
            # A previous allowed operation can legitimately advance updatedAt.
            # It must still be the same remote object before a second, distinct
            # allowlisted field family is changed.
            expected_id = _operation_remote_id(operation)
            if expected_id is None or current_ids.get(target) != expected_id:
                raise _apply_error("operation_precondition", f"remote target changed identity for {target}")
        elif not operation_precondition_holds(operation, current, created=frozenset(created)):
            raise _apply_error("operation_precondition", f"remote precondition no longer holds for {operation['target']}")
        resolved = _resolve_operation(operation, resolved_ids)
        try:
            response = transport.execute(resolved)
        except AppError as error:
            if error.category not in {"transport", "service"}:
                raise
            if not str(operation["kind"]).endswith(".create"):
                # A pre-existing update target proves nothing about whether an
                # ambiguous update reached Linear. Never mark it recovered or
                # retry it automatically.
                raise
            # The server may have accepted the create before its response was
            # lost.  Read identity before any retry; this implementation never
            # automatically re-sends a mutation.
            recovered_snapshot = snapshot_provider()
            recovered_id = _snapshot_ids(recovered_snapshot).get(target)
            expected_create_id = _create_input_id(operation)
            if recovered_id != expected_create_id:
                raise
            resolved_ids[target] = recovered_id
            created.add(target)
            changed.add(target)
            recovered.append(str(operation["id"]))
            continue
        remote_id = _response_id(response) or _snapshot_ids(snapshot_provider()).get(target)
        if remote_id is not None:
            resolved_ids[target] = remote_id
        if str(operation["kind"]).endswith(".create"):
            expected_create_id = _create_input_id(operation)
            if remote_id != expected_create_id:
                raise _apply_error("create_unverified", "create response/read-back did not match the planned input.id UUID")
            created.add(target)
        changed.add(target)
        applied.append(str(operation["id"]))

    final_snapshot = snapshot_provider()
    final_ids = _snapshot_ids(final_snapshot)
    if any(final_ids.get(identity) != remote_id for identity, remote_id in resolved_ids.items() if identity in created):
        raise _post_apply_error("post_apply_visibility", "post-apply verification could not find each created bridge resource")
    if post_verify is not None and not post_verify(final_snapshot):
        raise _post_apply_error("post_apply_verification", "post-apply verification found a remaining bridge-owned difference")
    return ApplyResult(tuple(applied), tuple(recovered), writes=len(applied))


def _operations(plan: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = plan.get("operations")
    if not isinstance(raw, list) or not all(isinstance(item, Mapping) for item in raw):
        raise _apply_error("plan_operations", "plan operations are invalid")
    ids = [item.get("id") for item in raw]
    if not all(isinstance(item, str) and item for item in ids) or len(set(ids)) != len(ids):
        raise _apply_error("plan_operation_ids", "plan operation IDs must be unique")
    return list(raw)


def _resolve_operation(operation: Mapping[str, object], ids: Mapping[str, str]) -> dict[str, object]:
    input_values = _mapping(operation.get("input"), "operation_input")
    return {**dict(operation), "input": _resolve_value(input_values, ids)}


def _resolve_value(value: object, ids: Mapping[str, str]) -> object:
    if isinstance(value, Mapping):
        if set(value) == {"$ref"}:
            identity = value.get("$ref")
            if not isinstance(identity, str) or identity not in ids:
                raise _apply_error("plan_reference", "plan references a resource that has not been safely resolved")
            return ids[identity]
        return {str(key): _resolve_value(nested, ids) for key, nested in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, ids) for item in value]
    return value


def _snapshot_ids(snapshot: Mapping[str, object]) -> dict[str, str]:
    resources = snapshot.get("resources")
    if not isinstance(resources, list):
        raise _apply_error("snapshot_resources", "snapshot resources are invalid")
    result: dict[str, str] = {}
    for item in resources:
        if not isinstance(item, Mapping) or not isinstance(item.get("identity"), str) or not isinstance(item.get("id"), str):
            raise _apply_error("snapshot_resource", "snapshot resource identities are invalid")
        result[str(item["identity"])] = str(item["id"])
    return result


def _response_id(response: Mapping[str, object]) -> str | None:
    # Production mutation adapters return ``{"id": ...}``; accepting a small
    # nested form makes fake GraphQL responses easy to model without broadening
    # the mutation contract.
    value = response.get("id")
    if isinstance(value, str) and value:
        return value
    resource = response.get("resource")
    if isinstance(resource, Mapping) and isinstance(resource.get("id"), str):
        return str(resource["id"])
    return None


def _operation_remote_id(operation: Mapping[str, object]) -> str | None:
    preconditions = operation.get("preconditions")
    if not isinstance(preconditions, Mapping):
        return None
    value = preconditions.get("id")
    return value if isinstance(value, str) and value else None


def _create_input_id(operation: Mapping[str, object]) -> str:
    input_values = operation.get("input")
    value = input_values.get("id") if isinstance(input_values, Mapping) else None
    if not isinstance(value, str) or not value:
        raise _apply_error("create_id", "create operation is missing its planned input.id UUID")
    return value


def _mapping(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _apply_error(code, "expected an object")
    return value


def _apply_error(code: str, message: str) -> AppError:
    return AppError(message, code=6, category="apply", diagnostics=[Diagnostic(code, message)])


def _post_apply_error(code: str, message: str) -> AppError:
    """Exit code 10: mutations were applied, but a fresh read afterward could
    not confirm the expected result."""

    return AppError(message, code=10, category="post_apply", diagnostics=[Diagnostic(code, message)])
