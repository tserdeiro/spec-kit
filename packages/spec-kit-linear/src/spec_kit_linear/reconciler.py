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
    failed_operation_id: str | None = None
    failed_operation_kind: str | None = None
    failed_operation_target: str | None = None
    unattempted_operation_ids: tuple[str, ...] = ()
    failure_phase: str | None = None
    failure_status: str | None = None

    def as_dict(self) -> dict[str, object]:
        result = {
            "applied_operation_ids": list(self.applied_operation_ids),
            "recovered_operation_ids": list(self.recovered_operation_ids),
            "writes": self.writes,
        }
        if self.failed_operation_id is not None:
            result.update({"failed_operation_id": self.failed_operation_id, "failed_operation_kind": self.failed_operation_kind, "failed_operation_target": self.failed_operation_target})
        if self.unattempted_operation_ids:
            result["unattempted_operation_ids"] = list(self.unattempted_operation_ids)
        if self.failure_phase is not None:
            result.update({"failure_phase": self.failure_phase, "failure_status": self.failure_status})
        return result


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
    operations = _operations(plan)
    try:
        initial = snapshot_provider()
    except AppError as error:
        _attach_failure(error, (), (), operations, None, "precondition", "rejected")
        raise
    if not snapshot_is_current(expected_snapshot, initial):
        error = _apply_error("snapshot_stale", "remote snapshot changed while planning; run push again")
        _attach_failure(error, (), (), operations, None, "precondition", "rejected")
        raise error
    try:
        resolved_ids = _snapshot_ids(initial)
    except AppError as error:
        _attach_failure(error, (), (), operations, None, "precondition", "rejected")
        raise
    created: set[str] = set()
    changed: set[str] = set()
    applied: list[str] = []
    recovered: list[str] = []

    for operation in operations:
        try:
            current = snapshot_provider()
        except AppError as error:
            _attach_failure(error, applied, recovered, operations, operation, "precondition", "rejected")
            raise
        # Existing resources from the rendered snapshot must be unchanged;
        # resources made by prior operations are intentionally excluded from
        # that immutable baseline and checked separately below.
        if not snapshot_is_current(expected_snapshot, current, ignored_identities=frozenset(changed)):
            error = _apply_error("snapshot_stale", "remote snapshot changed before the next mutation")
            _attach_failure(error, applied, recovered, operations, operation, "precondition", "rejected")
            raise error
        try:
            current_ids = _snapshot_ids(current)
        except AppError as error:
            _attach_failure(error, applied, recovered, operations, operation, "precondition", "rejected")
            raise
        for identity in created:
            expected_id = resolved_ids.get(identity)
            if expected_id is None or current_ids.get(identity) != expected_id:
                error = _apply_error("create_not_visible", "a previous create was not visible during mandatory revalidation")
                _attach_failure(error, applied, recovered, operations, operation, "precondition", "rejected")
                raise error
        target = str(operation["target"])
        if target in changed:
            # A previous allowed operation can legitimately advance updatedAt.
            # It must still be the same remote object before a second, distinct
            # allowlisted field family is changed.
            expected_id = _operation_remote_id(operation)
            if expected_id is None or current_ids.get(target) != expected_id:
                error = _apply_error("operation_precondition", f"remote target changed identity for {target}")
                _attach_failure(error, applied, recovered, operations, operation, "precondition", "rejected")
                raise error
        elif not operation_precondition_holds(operation, current, created=frozenset(created)):
            error = _apply_error("operation_precondition", f"remote precondition no longer holds for {operation['target']}")
            _attach_failure(error, applied, recovered, operations, operation, "precondition", "rejected")
            raise error
        try:
            resolved = _resolve_operation(operation, resolved_ids)
        except AppError as error:
            _attach_failure(error, applied, recovered, operations, operation, "precondition", "rejected")
            raise
        try:
            response = transport.execute(resolved)
        except AppError as error:
            if error.category not in {"transport", "service"}:
                status = "rejected" if _explicit_mutation_rejection(error) else "unconfirmed"
                _attach_failure(error, applied, recovered, operations, operation, "mutation", status)
                raise
            if not str(operation["kind"]).endswith(".create"):
                # A pre-existing update target proves nothing about whether an
                # ambiguous update reached Linear. Never mark it recovered or
                # retry it automatically.
                _attach_failure(error, applied, recovered, operations, operation, "mutation", "unconfirmed")
                raise
            # The server may have accepted the create before its response was
            # lost.  Read identity before any retry; this implementation never
            # automatically re-sends a mutation.
            try:
                recovered_snapshot = snapshot_provider()
            except AppError as recovery_error:
                _attach_failure(recovery_error, applied, recovered, operations, operation, "mutation", "unconfirmed")
                raise
            try:
                recovered_id = _snapshot_ids(recovered_snapshot).get(target)
            except AppError as recovery_error:
                _attach_failure(recovery_error, applied, recovered, operations, operation, "mutation", "unconfirmed")
                raise
            expected_create_id = _create_input_id(operation)
            if recovered_id != expected_create_id:
                _attach_failure(error, applied, recovered, operations, operation, "mutation", "unconfirmed")
                raise
            resolved_ids[target] = recovered_id
            created.add(target)
            changed.add(target)
            recovered.append(str(operation["id"]))
            continue
        try:
            remote_id = _response_id(response) or _snapshot_ids(snapshot_provider()).get(target)
        except AppError as error:
            _attach_failure(error, applied, recovered, operations, operation, "mutation", "unconfirmed")
            raise
        if remote_id is not None:
            resolved_ids[target] = remote_id
        if str(operation["kind"]).endswith(".create"):
            expected_create_id = _create_input_id(operation)
            if remote_id != expected_create_id:
                error = _apply_error("create_unverified", "create response/read-back did not match the planned input.id UUID")
                _attach_failure(error, applied, recovered, operations, operation, "mutation", "unconfirmed")
                raise error
            created.add(target)
        changed.add(target)
        applied.append(str(operation["id"]))

    try:
        final_snapshot = snapshot_provider()
    except AppError as error:
        _attach_failure(error, applied, recovered, operations, None, "postverification", "unconfirmed")
        raise
    try:
        final_ids = _snapshot_ids(final_snapshot)
    except AppError as error:
        _attach_failure(error, applied, recovered, operations, None, "postverification", "unconfirmed")
        raise
    if any(final_ids.get(identity) != remote_id for identity, remote_id in resolved_ids.items() if identity in created):
        error = _post_apply_error("post_apply_visibility", "post-apply verification could not find each created bridge resource")
        _attach_failure(error, applied, recovered, operations, None, "postverification", "unconfirmed")
        raise error
    try:
        verified = post_verify(final_snapshot) if post_verify is not None else True
    except AppError as error:
        _attach_failure(error, applied, recovered, operations, None, "postverification", "unconfirmed")
        raise
    if not verified:
        error = _post_apply_error("post_apply_verification", "post-apply verification found a remaining bridge-owned difference")
        _attach_failure(error, applied, recovered, operations, None, "postverification", "unconfirmed")
        raise error
    return ApplyResult(tuple(applied), tuple(recovered), writes=len(applied) + len(recovered))


def _attach_failure(error: AppError, applied: list[str] | tuple[str, ...], recovered: list[str] | tuple[str, ...], operations: list[Mapping[str, object]], failed: Mapping[str, object] | None, phase: str, status: str) -> None:
    failed_id = str(failed["id"]) if failed is not None else None
    if failed is None:
        start = 0 if phase == "precondition" else len(operations)
    else:
        # Preconditions are rejected before the request. Mutation rejection
        # means the request was sent but Linear declined it, so that operation
        # is not unattempted; an unconfirmed request may also have reached it.
        start = operations.index(failed) + (0 if phase == "precondition" else 1)
    result = ApplyResult(tuple(applied), tuple(recovered), len(applied) + len(recovered), failed_id,
                         str(failed["kind"]) if failed is not None else None,
                         str(failed["target"]) if failed is not None else None,
                         tuple(str(item["id"]) for item in operations[start:]), phase, status)
    error.apply_results = [result]


def _explicit_mutation_rejection(error: AppError) -> bool:
    for diagnostic in error.diagnostics:
        if diagnostic.code in {"mutation_rejected", "linear_auth", "linear_rate_limit"}:
            return True
        if diagnostic.code == "linear_http" and diagnostic.message.startswith("HTTP "):
            try:
                return 400 <= int(diagnostic.message.split()[1]) < 500
            except (IndexError, ValueError):
                pass
    return False


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
