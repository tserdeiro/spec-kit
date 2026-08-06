"""Shared/local configuration resolution, read once from the operator's own ref."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .env_files import ENV_PREFIX, EnvSnapshot
from .errors import EXIT_CONFIGURATION, AppError, Diagnostic
from .process import sha256_text


ROOT_CONFIG_FILENAME = "speckit-code-review.yml"
LOCAL_CONFIG_FILENAME = "speckit-code-review.local.yml"
CONFIG_ENV_VAR = f"{ENV_PREFIX}CONFIG"
EVIDENCE_DIR_ENV_VAR = f"{ENV_PREFIX}EVIDENCE_DIR"
STRICT_ENV_VAR = f"{ENV_PREFIX}STRICT"
LOG_LEVEL_ENV_VAR = f"{ENV_PREFIX}LOG_LEVEL"

# Doc "Reglas versionadas del repositorio consumidor": fixed in v0.x, on
# purpose. A configurable path would break the parity that motivates the
# choice -- `ocr` by hand, the OCR agent plugin, and this extension all reading
# the same file.
RULE_RELATIVE_PATH = ".opencodereview/rule.json"

SUPPORTED_SCHEMA_VERSION = "1.0"
PUBLISH_EVENTS = ("comment", "request-changes")

SECRET_KEY_RE = re.compile(r"(?:api[_-]?key|token|secret|password|credential|operator|identity)", re.IGNORECASE)
EXECUTABLE_KEY_RE = re.compile(r"(?:^|_)(?:bin|binary|executable|path_to)(?:$|_)|(?:ocr|gh|git)_bin", re.IGNORECASE)
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": SUPPORTED_SCHEMA_VERSION,
    "repository": {"slug": None, "github": None, "remote": "origin"},
    "engine": {
        "ocr_version": "v1.8.3",
        "rule_batch_size": 100,
        "timeout_seconds": 300,
    },
    "packet": {
        "max_bytes_per_artifact": 60000,
        "max_total_bytes": 400000,
        "include_checklists": True,
        "include_pr_body": True,
    },
    "budget": {"limit": 400},
    "publish": {
        "event": "request-changes",
        "batch_size": 25,
        "max_inline_comments": 100,
        "max_listed_files": 3000,
        "max_scanned_comments": 300,
        "summary_marker": "speckit-code-review:summary",
    },
    "evidence": {"keep_sessions": 20},
}

LOCAL_CONFIG_TEMPLATE = """\
# Local overrides for spec-kit-code-review. This file is gitignored: it holds
# machine preferences only -- never delivery state, never an authoritative
# source, never a credential, and never an executable path.
#
# evidence.root (optional): the evidence root for this machine. It must resolve
# outside the consumer repository and outside every active worktree of it; a
# path inside is rejected with exit code 2. Defaults to
# ${XDG_STATE_HOME:-~/.local/state}/tserdeiro/spec-kit/code-review.
#
# evidence:
#   root: "/absolute/path/outside/this/repository"
#
# log_level (optional): verbosity of this extension's own diagnostics.
#
# local:
#   log_level: "info"
"""


@dataclass(frozen=True)
class ResolvedConfig:
    """The frozen configuration that governs a whole session."""

    values: dict[str, Any]
    shared_path: Path | None
    local_path: Path | None
    sha256: str
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def section(self, name: str) -> dict[str, Any]:
        value = self.values.get(name)
        return value if isinstance(value, dict) else {}

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.section(section).get(key, default)


# -- the narrow YAML subset -------------------------------------------------


def _without_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
        if char == "#" and quote is None:
            return value[:index]
    return value


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return _unescape_double_quoted(value[1:-1])
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "~"}:
        return None
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    return value


def _unescape_double_quoted(value: str) -> str:
    result: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        result.append(char)
    return "".join(result)


def load_yaml_subset(path: Path) -> dict[str, Any]:
    """Load the mapping-and-scalar-list YAML subset this extension's config uses.

    Deliberately narrow: nested mappings, scalar leaves, and sequences of
    scalars (the budget globs and generated markers). No aliases, no tags, no
    nested sequences, nothing executable. A twenty-line configuration file is
    not worth a runtime dependency.
    """

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise AppError(
            f"configuration file not found: {path}",
            code=EXIT_CONFIGURATION,
            diagnostics=[Diagnostic("config_missing", "configuration file is required", str(path))],
        ) from error
    except UnicodeDecodeError as error:
        raise AppError(
            f"configuration is not UTF-8: {path}",
            code=EXIT_CONFIGURATION,
            diagnostics=[Diagnostic("config_encoding", "configuration must be UTF-8", str(path))],
        ) from error

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    sequence: tuple[int, list[Any]] | None = None
    key_re = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:[ ]*(.*))?$")

    for line_number, raw_line in enumerate(lines, start=1):
        if "\t" in raw_line:
            raise _yaml_error(path, line_number, "tabs are not supported")
        visible = _without_comment(raw_line).rstrip()
        if not visible.strip():
            continue
        indent = len(visible) - len(visible.lstrip(" "))
        if indent % 2:
            raise _yaml_error(path, line_number, "indentation must use multiples of two spaces")
        body = visible[indent:]

        if body.startswith("- "):
            if sequence is None or indent < sequence[0]:
                raise _yaml_error(path, line_number, "a sequence item must follow its key")
            sequence[1].append(_parse_scalar(body[2:]))
            continue

        sequence = None
        match = key_re.match(body)
        if not match:
            raise _yaml_error(path, line_number, "expected a mapping entry in the supported YAML subset")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise _yaml_error(path, line_number, "invalid indentation")
        parent = stack[-1][1]
        key, raw_value = match.group(1), match.group(2)
        if key in parent:
            raise _yaml_error(path, line_number, f"duplicate key: {key}")
        if raw_value is None or raw_value == "":
            # An empty value opens either a nested mapping or a sequence; the
            # next non-blank line decides which, so both are staged here.
            child: dict[str, Any] = {}
            items: list[Any] = []
            parent[key] = child
            stack.append((indent, child))
            sequence = (indent, items)
            parent[key] = _PendingBlock(child, items)
        else:
            parent[key] = _parse_scalar(raw_value)
    return _resolve_pending(root)


class _PendingBlock:
    """A block whose kind (mapping or sequence) the next line decides."""

    __slots__ = ("mapping", "sequence")

    def __init__(self, mapping: dict[str, Any], sequence: list[Any]) -> None:
        self.mapping = mapping
        self.sequence = sequence


def _resolve_pending(value: Any) -> Any:
    if isinstance(value, _PendingBlock):
        if value.sequence:
            return list(value.sequence)
        return _resolve_pending(value.mapping)
    if isinstance(value, dict):
        return {key: _resolve_pending(nested) for key, nested in value.items()}
    return value


def dump_yaml_subset(data: Mapping[str, Any]) -> str:
    """Serialize a mapping back into the YAML subset :func:`load_yaml_subset` reads."""

    lines: list[str] = []
    _dump_mapping(data, indent=0, lines=lines)
    return "\n".join(lines) + "\n"


def _dump_mapping(data: Mapping[str, Any], *, indent: int, lines: list[str]) -> None:
    pad = " " * indent
    for key, value in data.items():
        if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
            raise ValueError(f"key {key!r} is outside the supported YAML subset")
        if isinstance(value, Mapping):
            lines.append(f"{pad}{key}:")
            _dump_mapping(value, indent=indent + 2, lines=lines)
        elif isinstance(value, list):
            lines.append(f"{pad}{key}:")
            for item in value:
                lines.append(f"{pad}  - {_dump_scalar(item)}")
        else:
            lines.append(f"{pad}{key}: {_dump_scalar(value)}")


def _dump_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    raise ValueError(f"unsupported YAML subset value: {value!r}")


def _yaml_error(path: Path, line: int, message: str) -> AppError:
    return AppError(
        f"invalid configuration at {path}:{line}: {message}",
        code=EXIT_CONFIGURATION,
        diagnostics=[Diagnostic("config_yaml", message, str(path), line)],
    )


def deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def find_keys(value: Any, pattern: re.Pattern[str], prefix: str = "") -> list[str]:
    hits: list[str] = []
    if not isinstance(value, dict):
        return hits
    for key, nested in value.items():
        location = f"{prefix}.{key}" if prefix else key
        if pattern.search(str(key)):
            hits.append(location)
        hits.extend(find_keys(nested, pattern, location))
    return hits


# -- resolution -------------------------------------------------------------


_TRUTHY = {"1", "true", "yes", "on"}
_VERBOSE_LOG_LEVELS = {"debug", "trace"}


def env_flag(environment: EnvSnapshot | None, key: str) -> bool:
    """Read a boolean ``SPECKIT_CODE_REVIEW_*`` value from the frozen snapshot.

    Only the documented truthy spellings enable a flag; ``0``, ``false``, an
    empty value, and anything unrecognized leave it off, so exporting
    ``SPECKIT_CODE_REVIEW_STRICT=0`` never silently turns strictness on.
    """

    if environment is None:
        return False
    value = environment.get(key)
    return bool(value) and str(value).strip().lower() in _TRUTHY


def env_verbose(environment: EnvSnapshot | None) -> bool:
    """Whether ``SPECKIT_CODE_REVIEW_LOG_LEVEL`` asks for verbose diagnostics."""

    if environment is None:
        return False
    value = environment.get(LOG_LEVEL_ENV_VAR)
    return bool(value) and str(value).strip().lower() in _VERBOSE_LOG_LEVELS


def shared_config_path(root: Path) -> Path:
    return root / ROOT_CONFIG_FILENAME


def local_config_path(root: Path) -> Path:
    return root / LOCAL_CONFIG_FILENAME


def resolve_config_path(root: Path, *, explicit: str | None = None, environment: EnvSnapshot | None = None) -> tuple[Path, str]:
    """Resolve the shared configuration path and say where the choice came from.

    Order, highest priority first: ``--config PATH``, ``SPECKIT_CODE_REVIEW_CONFIG``,
    ``<root>/speckit-code-review.yml``. There is no legacy path.
    """

    if explicit:
        return Path(explicit).expanduser(), "flag"
    from_environment = environment.get(CONFIG_ENV_VAR) if environment is not None else None
    if from_environment:
        return Path(from_environment).expanduser(), "environment"
    return shared_config_path(root), "root"


def load_config(
    root: Path,
    *,
    explicit: str | None = None,
    environment: EnvSnapshot | None = None,
) -> ResolvedConfig:
    """Load and validate the effective configuration, once, and freeze it.

    Doc "Precedencia y momento de lectura de la configuracion": this happens
    from the operator's original ref, before any execution environment is
    prepared, and the result governs the whole session. Configuration present
    in the candidate's head is never read.
    """

    shared_path, source = resolve_config_path(root, explicit=explicit, environment=environment)
    diagnostics: list[Diagnostic] = []
    values = deepcopy(DEFAULT_CONFIG)
    resolved_shared: Path | None = None

    if shared_path.is_file():
        shared_values = load_yaml_subset(shared_path)
        _validate_shared(shared_values, shared_path)
        values = deep_merge(values, shared_values)
        resolved_shared = shared_path
    elif explicit or source == "environment":
        raise AppError(
            f"configuration file not found: {shared_path}",
            code=EXIT_CONFIGURATION,
            diagnostics=[Diagnostic("config_missing", "the explicitly selected configuration file does not exist", str(shared_path))],
        )
    else:
        diagnostics.append(
            Diagnostic(
                "config_absent",
                f"no {ROOT_CONFIG_FILENAME} found; defaults are in effect (run doctor --fix to create one)",
                str(shared_path),
                severity="warning",
            )
        )

    local_path = local_config_path(root)
    resolved_local: Path | None = None
    if local_path.is_file():
        local_values = load_yaml_subset(local_path)
        _validate_local(local_values, local_path)
        values = deep_merge(values, local_values)
        resolved_local = local_path

    _validate_effective(values, resolved_shared or shared_path)
    return ResolvedConfig(
        values=values,
        shared_path=resolved_shared,
        local_path=resolved_local,
        sha256=sha256_text(dump_yaml_subset(values)),
        diagnostics=tuple(diagnostics),
    )


def _validate_shared(values: Mapping[str, Any], path: Path) -> None:
    """The committed file may hold no secret, no operator identity, and no machine path."""

    secrets = find_keys(values, SECRET_KEY_RE)
    if secrets:
        raise AppError(
            f"shared configuration contains forbidden keys: {', '.join(sorted(secrets))}",
            code=EXIT_CONFIGURATION,
            diagnostics=[
                Diagnostic("config_secret_key", "credentials and operator identity never belong in the committed configuration", str(path))
            ],
        )
    evidence = values.get("evidence")
    if isinstance(evidence, dict) and "root" in evidence:
        raise AppError(
            "evidence.root belongs in the local configuration, not the shared one",
            code=EXIT_CONFIGURATION,
            diagnostics=[Diagnostic("config_evidence_root_shared", "evidence.root is a machine path", str(path))],
        )


def _validate_local(values: Mapping[str, Any], path: Path) -> None:
    """The local overlay may never carry an executable path."""

    executables = find_keys(values, EXECUTABLE_KEY_RE)
    if executables:
        raise AppError(
            f"local configuration may not define executable paths: {', '.join(sorted(executables))}",
            code=EXIT_CONFIGURATION,
            diagnostics=[
                Diagnostic(
                    "config_executable_path",
                    "ocr, gh, and git are resolved only from PATH or the trusted environment overrides",
                    str(path),
                )
            ],
        )


def _validate_effective(values: Mapping[str, Any], path: Path) -> None:
    schema_version = values.get("schema_version")
    if str(schema_version) != SUPPORTED_SCHEMA_VERSION:
        raise AppError(
            f"unsupported configuration schema_version: {schema_version}",
            code=EXIT_CONFIGURATION,
            diagnostics=[Diagnostic("config_schema_version", f"expected {SUPPORTED_SCHEMA_VERSION}", str(path))],
        )

    publish = values.get("publish") if isinstance(values.get("publish"), dict) else {}
    event = publish.get("event", "request-changes")
    if event == "approve":
        raise AppError(
            "publish.event: approve is not a valid value",
            code=EXIT_CONFIGURATION,
            diagnostics=[Diagnostic("publish_event_approve", "approving a pull request is always a human decision", str(path))],
        )
    if event not in PUBLISH_EVENTS:
        raise AppError(
            f"unsupported publish.event: {event}",
            code=EXIT_CONFIGURATION,
            diagnostics=[Diagnostic("publish_event_invalid", f"expected one of {', '.join(PUBLISH_EVENTS)}", str(path))],
        )

    for section, key in (
        ("engine", "rule_batch_size"),
        ("engine", "timeout_seconds"),
        ("packet", "max_bytes_per_artifact"),
        ("packet", "max_total_bytes"),
        ("budget", "limit"),
        ("publish", "batch_size"),
        ("publish", "max_inline_comments"),
        ("publish", "max_listed_files"),
        ("publish", "max_scanned_comments"),
        ("evidence", "keep_sessions"),
    ):
        block = values.get(section) if isinstance(values.get(section), dict) else {}
        if key not in block:
            continue
        value = block[key]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise AppError(
                f"{section}.{key} must be a positive integer",
                code=EXIT_CONFIGURATION,
                diagnostics=[Diagnostic("config_integer", f"{section}.{key} = {value!r}", str(path))],
            )


def shared_config_document(*, repository: str | None, remote: str, slug: str | None) -> dict[str, Any]:
    """The committed configuration ``install`` writes, derived from the defaults."""

    document = deepcopy(DEFAULT_CONFIG)
    document["repository"] = {
        "slug": slug or (repository.split("/")[-1] if repository else None),
        "github": repository,
        "remote": remote,
    }
    return document
