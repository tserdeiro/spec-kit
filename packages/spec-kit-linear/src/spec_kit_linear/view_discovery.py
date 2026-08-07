"""Read-only adoption of the two conventional Shared Views by name.

A repository owns two Shared Views: ``<slug> / Features`` (a Project view)
and ``<slug> / Work`` (an Issue view).
``onboard`` resolves these by name instead of requiring an operator to
already know their UUIDs: 0 matches warns and leaves the field unset (create
the view by hand in Linear); 2+ matches always aborts; exactly 1 match must
be ``shared`` and have the expected model type, or it aborts too. This
module never mutates Linear.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import AppError, Diagnostic
from .linear_client import LinearClient

_VIEW_SPECS: tuple[tuple[str, str, str], ...] = (
    ("Features", "project", "project_view_id"),
    ("Work", "issue", "issue_view_id"),
)


@dataclass(frozen=True)
class ViewAdoptionResult:
    resolved: dict[str, str]
    diagnostics: tuple[Diagnostic, ...]


def conventional_view_name(slug: str, suffix: str) -> str:
    return f"{slug} / {suffix}"


def resolve_shared_views_by_name(client: LinearClient, slug: str) -> ViewAdoptionResult:
    """Resolve ``<slug> / Features`` and ``<slug> / Work`` by name, read-only."""

    diagnostics: list[Diagnostic] = []
    resolved: dict[str, str] = {}
    for suffix, expected_type, field in _VIEW_SPECS:
        name = conventional_view_name(slug, suffix)
        matches = client.find_shared_views_by_name(name)
        if not matches:
            diagnostics.append(
                Diagnostic(
                    "shared_view_missing",
                    f"no Shared View named '{name}' was found; onboard creates it when it applies",
                    severity="warning",
                )
            )
            continue
        if len(matches) > 1:
            raise AppError(
                f"multiple Shared Views match name '{name}'",
                code=6,
                category="remote_identity",
                diagnostics=[Diagnostic("shared_view_ambiguous", f"'{name}' does not resolve to exactly one Shared View")],
            )
        match = matches[0]
        if match.type.lower() != expected_type or match.shared is not True:
            raise AppError(
                f"the Shared View named '{name}' is not a shared {expected_type} view",
                code=6,
                category="remote_identity",
                diagnostics=[Diagnostic("shared_view_type_mismatch", f"'{name}' must be a shared {expected_type} view")],
            )
        resolved[field] = match.id
        diagnostics.append(Diagnostic("shared_view_adopted", f"adopted Shared View '{name}' ({match.id})", severity="info"))
    return ViewAdoptionResult(resolved=resolved, diagnostics=tuple(diagnostics))
