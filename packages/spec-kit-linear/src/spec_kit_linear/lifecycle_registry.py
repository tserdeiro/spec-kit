"""Read-only comparison of Spec Kit's native lifecycle hook registry against
this extension's own manifest declarations.

Doc "speckit.linear.install": "valida los lifecycle hooks que `specify
extension add` registro desde el manifest, sin registrarlos de nuevo" and
"Lifecycle hooks": "Una reinstalacion de la extension puede volver a
materializar hooks habilitados. `doctor` debe detectar la divergencia y
`install --restore-hook-state` debe reaplicar explicitamente la politica
local persistida, sin registrar hooks manualmente ni mutar Linear."

This module never writes `.specify/extensions.yml` -- that file belongs
entirely to Spec Kit's own extension installation machinery. The comparison
here is purely diagnostic: a missing or unparseable registry does not block
`doctor` or `install`, since the registry's presence/shape is Spec Kit's
responsibility, not this extension's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import Diagnostic

EXTENSION_ID = "linear"
# Kept in sync with this extension's own extension.yml `hooks:` section
# (six lifecycle events, all mapped to speckit.linear.push).
MANAGED_LIFECYCLE_EVENTS: tuple[str, ...] = (
    "after_specify",
    "after_clarify",
    "after_plan",
    "after_tasks",
    "after_implement",
    "after_analyze",
)
MANAGED_LIFECYCLE_COMMAND = "speckit.linear.push"

REGISTRY_RELATIVE_PATH = Path(".specify/extensions.yml")


def registry_path(root: Path) -> Path:
    return root / REGISTRY_RELATIVE_PATH


def load_registry(root: Path) -> dict[str, Any] | None:
    """Best-effort read of the native registry; ``None`` when absent or unparseable."""

    path = registry_path(root)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        return _parse_registry_yaml(text)
    except ValueError:
        return None


def registry_diagnostics(registry: dict[str, Any] | None, *, lifecycle_enabled: bool) -> list[Diagnostic]:
    """Compare the registry's hook entries for this extension against its manifest.

    Reports, without ever writing anything:
    - events the manifest declares that Spec Kit has not (yet) registered;
    - the "reinstall re-enables a hook the persisted local gate disabled"
      divergence the doc calls out explicitly.
    """

    if registry is None:
        return [
            Diagnostic(
                "lifecycle_registry_missing",
                "Spec Kit's native hook registry (.specify/extensions.yml) was not found; lifecycle hooks may not be registered yet",
                severity="info",
            )
        ]
    hooks = registry.get("hooks")
    hooks = hooks if isinstance(hooks, dict) else {}
    missing: list[str] = []
    disagreeing: list[str] = []
    for event in MANAGED_LIFECYCLE_EVENTS:
        entries = hooks.get(event)
        entries = entries if isinstance(entries, list) else []
        match = next(
            (
                item
                for item in entries
                if isinstance(item, dict) and item.get("extension") == EXTENSION_ID and item.get("command") == MANAGED_LIFECYCLE_COMMAND
            ),
            None,
        )
        if match is None:
            missing.append(event)
        elif match.get("enabled") is True and not lifecycle_enabled:
            disagreeing.append(event)

    diagnostics: list[Diagnostic] = []
    if missing:
        diagnostics.append(
            Diagnostic(
                "lifecycle_registry_unregistered",
                f"{len(missing)} lifecycle hook(s) declared in extension.yml are not registered by Spec Kit yet: {', '.join(missing)}; "
                "run `specify extension add` (again) to register them -- this extension never registers hooks itself",
                severity="warning",
            )
        )
    if disagreeing:
        diagnostics.append(
            Diagnostic(
                "lifecycle_registry_divergence",
                f"Spec Kit's native registry shows {len(disagreeing)} lifecycle hook(s) as enabled ({', '.join(disagreeing)}), "
                "but the persisted local gate hooks.lifecycle_enabled is false; `push --hook` still no-ops -- "
                "the local gate remains authoritative regardless of what a reinstall re-materializes",
                severity="info",
            )
        )
    if not missing and not disagreeing:
        diagnostics.append(
            Diagnostic("lifecycle_registry_ok", "Spec Kit's native hook registry matches this extension's declared lifecycle hooks", severity="info")
        )
    return diagnostics


def _parse_scalar_value(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "~", ""}:
        return None
    return value


def _parse_registry_yaml(text: str) -> dict[str, Any]:
    """Minimal recursive-descent reader for the small YAML subset Spec Kit
    emits for `.specify/extensions.yml`: nested mappings, and lists of either
    scalars or flat mappings, with a list's items optionally at the *same*
    indentation as their owning key (Spec Kit's own style) as well as more
    deeply indented (the more common style elsewhere)."""

    entries: list[tuple[int, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        entries.append((indent, stripped))

    position = 0

    def parse_mapping(indent: int) -> dict[str, Any]:
        nonlocal position
        result: dict[str, Any] = {}
        while position < len(entries) and entries[position][0] == indent and not entries[position][1].startswith("- "):
            content = entries[position][1]
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()
            position += 1
            if value:
                result[key] = _parse_scalar_value(value)
            elif position < len(entries) and entries[position][0] >= indent and entries[position][1].startswith("- "):
                result[key] = parse_list(entries[position][0])
            elif position < len(entries) and entries[position][0] > indent:
                result[key] = parse_mapping(entries[position][0])
            else:
                result[key] = {}
        return result

    def parse_list(indent: int) -> list[Any]:
        nonlocal position
        items: list[Any] = []
        while position < len(entries) and entries[position][0] == indent and entries[position][1].startswith("- "):
            rest = entries[position][1][2:]
            if ":" in rest:
                key, _, value = rest.partition(":")
                key = key.strip()
                value = value.strip()
                item: dict[str, Any] = {}
                position += 1
                item[key] = _parse_scalar_value(value) if value else {}
                child_indent = indent + 2
                while position < len(entries) and entries[position][0] == child_indent and not entries[position][1].startswith("- "):
                    sub_key, _, sub_value = entries[position][1].partition(":")
                    item[sub_key.strip()] = _parse_scalar_value(sub_value.strip())
                    position += 1
                items.append(item)
            else:
                items.append(_parse_scalar_value(rest))
                position += 1
        return items

    return parse_mapping(0)
