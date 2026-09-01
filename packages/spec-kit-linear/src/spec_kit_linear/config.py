"""Own local configuration loader; it intentionally does not use specify-cli internals."""

from __future__ import annotations

import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .domain import RepositoryBinding
from .endpoint import ENDPOINT_ENV
from .errors import AppError, Diagnostic


# The one shared configuration file, at the consumer repository root and
# committed by default: it carries no secrets (SECRET_KEY_RE rejects those
# unconditionally), so one operator onboards a repository once and
# teammates/CI inherit the binding from Git. `onboard` regenerates it from
# remote truth on demand.
ROOT_CONFIG_FILENAME = "speckit-linear.yml"

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# The exact ID value `config/speckit-linear.template.yml` ships in every ID
# field. Finding it in a loaded config means `onboard` never bound this
# repository, and the diagnosis must land before any network call (plan D7):
# validate_config rejects it ahead of the per-field UUID checks, whose bare
# "must be a UUID" would not name the remediation.
PLACEHOLDER_ID = "00000000-0000-0000-0000-000000000000"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SECRET_KEY_RE = re.compile(r"(?:api[_-]?key|token|secret|password|operator|identity)", re.IGNORECASE)


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
    return value


def _unescape_double_quoted(value: str) -> str:
    """Reverse ``dump_yaml_subset``'s backslash-escaping of ``\\`` and ``"``.

    ``_without_comment`` already tracks these same escapes so an escaped
    quote inside a double-quoted value is never mistaken for its closing
    quote or for a comment start; this only removes the escaping once that
    quote-aware comment stripping is done and the surrounding quotes are
    already known to bound the whole value.
    """

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
    """Load the small mapping-only YAML subset used by this extension's config.

    The parser is deliberately narrow: no aliases, tags, lists, or executable
    YAML features are accepted. Stage 1 needs a predictable configuration
    surface and avoids adding a runtime dependency solely for YAML.
    """

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise AppError(
            f"repository is not linked to Linear — run onboard to bind it (expected {path})",
            code=3,
            category="configuration",
            diagnostics=[Diagnostic("config_missing", "run onboard to create the configuration and bind this repository", str(path))],
        ) from error
    except UnicodeDecodeError as error:
        raise AppError(
            f"configuration is not UTF-8: {path}",
            code=3,
            category="configuration",
            diagnostics=[Diagnostic("config_encoding", "configuration must be UTF-8", str(path))],
        ) from error

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
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
        match = key_re.match(visible[indent:])
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
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(raw_value)
    return root


_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def dump_yaml_subset(data: Mapping[str, Any]) -> str:
    """Serialize a mapping back into the YAML subset :func:`load_yaml_subset` reads.

    Deliberately narrow, matching the loader: mapping-only nesting with
    2-space indentation, scalar leaves (``str``/``bool``/``None``). Every
    string leaf is quoted, matching the prevailing style already committed
    in ``config/linear-config.template.yml`` and the test fixtures, and
    sidesteps every quoting edge case the loader has (``#`` truncating an
    unquoted value as a comment, an empty string being indistinguishable
    from a nested empty mapping, a bare ``true``/``false``/``null`` being
    read back as a boolean or null). Key order is preserved from the input
    mapping so a caller building an overlay with :func:`deep_merge` keeps a
    stable, re-diffable file across repeated ``install`` runs.
    """

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
        else:
            lines.append(f"{pad}{key}: {_dump_scalar(value)}")


def _dump_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    raise ValueError(f"unsupported YAML subset value: {value!r}")


def _yaml_error(path: Path, line: int, message: str) -> AppError:
    return AppError(
        f"invalid configuration at {path}:{line}: {message}",
        code=3,
        category="configuration",
        diagnostics=[Diagnostic("config_yaml", message, str(path), line)],
    )


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def find_secret_keys(value: Any, prefix: str = "") -> list[str]:
    """Locate secret/identity-shaped keys anywhere in a loaded config.

    Sequences are walked too, with the index in the reported location: a
    mapping nested inside a list is still a mapping a person can write, and a
    scan that only descends through mappings would let ``linear: [{token:
    ...}]`` past a check whose whole job is to be exhaustive.
    """

    hits: list[str] = []
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            hits.extend(find_secret_keys(item, f"{prefix}[{index}]"))
        return hits
    if not isinstance(value, dict):
        return hits
    for key, nested in value.items():
        location = f"{prefix}.{key}" if prefix else key
        if SECRET_KEY_RE.search(key):
            hits.append(location)
        hits.extend(find_secret_keys(nested, location))
    return hits


# doc "Cliente GraphQL" > "Override de endpoint": the GraphQL destination is
# an environment value and nothing else, so an endpoint key in the shared
# *or* the local file is exit code 3, never a warning.
#
# To be precise about what this does and does not do: no loader in this
# package has ever read a destination out of a configuration file, so this
# closes no currently-open hole. It is defense in depth plus a legible error.
# Its value is in what happens to the person who reasonably assumes the
# destination is configurable and writes `linear.endpoint:` in the committed
# file: without this they get silence and a run against production; with it
# they get an error naming the file, the key, and the environment variable
# that actually works. It also fixes the shape of the rule ahead of any
# future loader change -- a committed, per-repository file able to redirect
# the reads and writes of a whole team would be a redirection vector wearing
# the costume of an innocuous configuration change, and the cheapest moment
# to forbid it is before anything reads it.
#
# The names below are what a person would plausibly reach for when trying to
# express "point this somewhere else" in YAML. Hyphens are normalized to
# underscores and matching is case-insensitive but exact (never a substring),
# so `linear.graphql-endpoint`, `Endpoint` and `linear.API_URL` are caught
# while a legitimate key that merely contains one of these words --
# `project_view_id` -- keeps working.
#
# Two tiers, because one of these words is already a legitimate, unrelated
# key: `repository.url` is the consumer's Git remote, not a GraphQL
# destination.
#
# Tier 1, rejected at any depth -- these can only ever mean the API
# destination: endpoint, endpoint_url, endpoints, graphql, graphql_api,
# graphql_server, graphql_endpoint, graphql_url, graphql_uri, api_endpoint,
# api_url, api_uri, api_base, api_host, api_root, linear_endpoint,
# linear_url, linear_api_url, workspace_url, instance_url, self_hosted_url,
# speckit_linear_graphql_endpoint.
#
# Tier 2, rejected only at the top level and directly under `linear` -- the
# places where such a key would mean "the Linear API", and nowhere else: address, api, base, base_url, base_uri, domain, host,
# hostname, origin, server, server_url, url, uri.
_ENDPOINT_KEY_NAMES = frozenset(
    {
        "endpoint",
        "endpoint_url",
        "endpoints",
        "graphql",
        "graphql_api",
        "graphql_server",
        "graphql_endpoint",
        "graphql_url",
        "graphql_uri",
        "api_endpoint",
        "api_url",
        "api_uri",
        "api_base",
        "api_host",
        "api_root",
        "linear_endpoint",
        "linear_url",
        "linear_api_url",
        "workspace_url",
        "instance_url",
        "self_hosted_url",
        "speckit_linear_graphql_endpoint",
    }
)
_ENDPOINT_AMBIGUOUS_KEY_NAMES = frozenset(
    {
        "address",
        "api",
        "base",
        "base_url",
        "base_uri",
        "domain",
        "host",
        "hostname",
        "origin",
        "server",
        "server_url",
        "url",
        "uri",
    }
)
_ENDPOINT_AMBIGUOUS_SCOPES = frozenset({"", "linear"})
def find_endpoint_keys(value: Any, prefix: str = "") -> list[str]:
    """Return the dotted locations of every endpoint-shaped key in ``value``.

    Sequences are walked with their index in the reported location, so a
    mapping written inside a list (``linear: [{endpoint: ...}]``) cannot slip
    past a scan whose entire purpose is to be exhaustive. A list index is
    never itself an ambiguous-tier scope: `linear[0].url` is still `linear`'s
    business, so the scope test looks through the index.
    """

    hits: list[str] = []
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            hits.extend(find_endpoint_keys(item, f"{prefix}[{index}]"))
        return hits
    if not isinstance(value, dict):
        return hits
    scope = re.sub(r"\[\d+\]", "", prefix)
    for key, nested in value.items():
        location = f"{prefix}.{key}" if prefix else key
        normalized = str(key).strip().lower().replace("-", "_")
        if normalized in _ENDPOINT_KEY_NAMES:
            hits.append(location)
        elif normalized in _ENDPOINT_AMBIGUOUS_KEY_NAMES and scope in _ENDPOINT_AMBIGUOUS_SCOPES:
            hits.append(location)
        hits.extend(find_endpoint_keys(nested, location))
    return hits


def reject_endpoint_keys(config: Any, source: Path) -> None:
    """Fail closed (code 3) when a configuration file tries to set the endpoint."""

    hits = find_endpoint_keys(config)
    if not hits:
        return
    raise AppError(
        "configuration must not set the Linear GraphQL endpoint",
        code=3,
        category="configuration",
        diagnostics=[
            Diagnostic(
                "config_endpoint",
                f"remove '{key}': the GraphQL destination comes only from {ENDPOINT_ENV} in the environment",
                str(source),
            )
            for key in hits
        ],
    )


def _mapping(config: dict[str, Any], name: str, source: Path) -> dict[str, Any]:
    value = config.get(name)
    if not isinstance(value, dict):
        raise AppError(
            f"configuration section '{name}' must be a mapping",
            code=3,
            category="configuration",
            diagnostics=[Diagnostic("config_section", f"'{name}' must be a mapping", str(source))],
        )
    return value


def _required_string(section: dict[str, Any], key: str, source: Path) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AppError(
            f"configuration value '{key}' is required",
            code=3,
            category="configuration",
            diagnostics=[Diagnostic("config_required", f"'{key}' must be a non-empty string", str(source))],
        )
    return value.strip()


def _required_uuid(section: dict[str, Any], key: str, source: Path) -> str:
    value = _required_string(section, key, source)
    if not UUID_RE.fullmatch(value):
        raise AppError(
            f"configuration value '{key}' must be a UUID",
            code=3,
            category="configuration",
            diagnostics=[Diagnostic("config_uuid", f"'{key}' must be a UUID", str(source))],
        )
    return value


def _optional_uuid(section: dict[str, Any], key: str, source: Path) -> None:
    if key in section:
        _required_uuid(section, key, source)


def resolve_config_path(root: Path, explicit_config: str | None) -> Path:
    """Resolve the shared config path.

    An explicit ``--config`` flag wins outright; ``SPECKIT_LINEAR_CONFIG``
    supplies the same override from the environment; otherwise the committed
    root config.
    """

    candidate = explicit_config or os.environ.get("SPECKIT_LINEAR_CONFIG")
    if candidate:
        path = Path(candidate).expanduser()
        return path if path.is_absolute() else root / path
    return root / ROOT_CONFIG_FILENAME


def load_config(
    root: Path,
    explicit_config: str | None = None,
    *,
    allow_unbound_repository: bool = False,
) -> tuple[dict[str, Any], Path]:
    """Load the shared config with a private loader; never uses specify-cli internals."""

    shared_path = resolve_config_path(root, explicit_config).resolve()
    config = load_yaml_subset(shared_path)
    reject_endpoint_keys(config, shared_path)
    secret_keys = find_secret_keys(config)
    if secret_keys:
        raise AppError(
            "shared configuration must not contain secrets or operator identity",
            code=3,
            category="configuration",
            diagnostics=[
                Diagnostic("config_secret", f"remove '{key}' from shared configuration", str(shared_path))
                for key in secret_keys
            ],
        )
    validate_config(config, shared_path, allow_unbound_repository=allow_unbound_repository)
    return config, shared_path


def validate_config(config: dict[str, Any], source: Path, *, allow_unbound_repository: bool = False) -> None:
    # Repeated here on the merged mapping so that the callers that validate a
    # config they built themselves (install/onboard, before writing it) are
    # covered too; load_config's per-file check runs first and gives the more
    # precise path.
    reject_endpoint_keys(config, source)
    if config.get("schema_version") != "1.0":
        raise AppError(
            "configuration schema_version must be '1.0'",
            code=3,
            category="configuration",
            diagnostics=[Diagnostic("config_schema", "schema_version must be '1.0'", str(source))],
        )
    linear = _mapping(config, "linear", source)
    repository = _mapping(config, "repository", source)
    if not allow_unbound_repository:
        _reject_placeholder_ids((("linear", linear), ("repository", repository)), source)
    _required_uuid(linear, "workspace_id", source)
    _required_uuid(linear, "team_id", source)
    _required_string(linear, "team_key", source)
    slug = _required_string(repository, "slug", source)
    if not SLUG_RE.fullmatch(slug):
        raise AppError(
            "repository.slug must use lowercase letters, numbers, and hyphens",
            code=3,
            category="configuration",
            diagnostics=[Diagnostic("config_slug", "repository.slug is invalid", str(source))],
        )
    if not allow_unbound_repository:
        _required_uuid(repository, "project_label_group_id", source)
        _required_uuid(repository, "project_label_id", source)
        _required_string(repository, "project_label", source)
        _required_uuid(repository, "project_view_id", source)
        _required_uuid(repository, "issue_view_id", source)
    _validate_lifecycle_section(config, source)
    _validate_hooks_section(config, source)


def _reject_placeholder_ids(sections: tuple[tuple[str, dict[str, Any]], ...], source: Path) -> None:
    """Fail closed (code 3) while the config still carries the template's zeroed IDs.

    Skipped under ``allow_unbound_repository`` so ``onboard`` can validate the
    merged config it is in the middle of binding.
    """

    placeholders = [
        f"{name}.{key}"
        for name, section in sections
        for key, value in section.items()
        if value == PLACEHOLDER_ID
    ]
    if not placeholders:
        return
    raise AppError(
        "configuration is still the template — run onboard to bind this repository",
        code=3,
        category="configuration",
        diagnostics=[
            Diagnostic("config_placeholder", f"'{key}' still carries the template placeholder; run onboard", str(source))
            for key in placeholders
        ],
    )


_HOOKS_KEYS = frozenset({"lifecycle_enabled", "auto_apply"})


def _validate_hooks_section(config: dict[str, Any], source: Path) -> None:
    hooks = config.get("hooks")
    if hooks is None:
        return
    if not isinstance(hooks, dict):
        raise AppError(
            "configuration section 'hooks' must be a mapping",
            code=3,
            category="configuration",
            diagnostics=[Diagnostic("config_section", "'hooks' must be a mapping", str(source))],
        )
    unknown = sorted(set(hooks) - _HOOKS_KEYS)
    if unknown:
        raise AppError(
            f"configuration section 'hooks' has unsupported key(s): {', '.join(unknown)}",
            code=3,
            category="configuration",
            diagnostics=[Diagnostic("config_hooks_key", f"unsupported hooks key(s): {', '.join(unknown)}", str(source))],
        )
    for key in sorted(_HOOKS_KEYS):
        if key in hooks and not isinstance(hooks[key], bool):
            raise AppError(
                f"configuration value 'hooks.{key}' must be a boolean",
                code=3,
                category="configuration",
                diagnostics=[Diagnostic("config_bool", f"'hooks.{key}' must be true or false", str(source))],
            )


def _validate_lifecycle_section(config: dict[str, Any], source: Path) -> None:
    """Validate the optional ``lifecycle`` section that maps task completion to Linear workflow states.

    The doc's example shared configuration (see "Configuración") omits this
    section entirely, so it is optional. When present, the two endpoint states
    are required together: a half-configured mapping is ambiguous rather than
    partially useful, so it is rejected the same way other malformed sections
    are rejected. When absent, ``planner._desired_state_id`` already returns
    ``None`` and no ``stateId``/``issue.lifecycle.update`` operation is ever
    produced; ``doctor`` reports that lifecycle sync is disabled.

    ``started_state_id`` and ``review_state_id`` carry the two intermediate
    states of vision steps 4-7. They are individually optional because a Team
    need not have both: a missing id simply leaves the tasks that derive to
    that state untouched (``review`` degrades to ``started`` first).
    """

    lifecycle = config.get("lifecycle")
    if lifecycle is None:
        return
    if not isinstance(lifecycle, dict):
        raise AppError(
            "configuration section 'lifecycle' must be a mapping",
            code=3,
            category="configuration",
            diagnostics=[Diagnostic("config_section", "'lifecycle' must be a mapping", str(source))],
        )
    _required_uuid(lifecycle, "completed_state_id", source)
    _required_uuid(lifecycle, "open_state_id", source)
    _optional_uuid(lifecycle, "started_state_id", source)
    _optional_uuid(lifecycle, "review_state_id", source)


def team_binding(config: Mapping[str, Any]) -> tuple[str, str]:
    """Return the bound Team's ``(id, key)``; both are required and validated.

    The key is what makes the bug/chore branch convention configurable: a
    branch is matched against ``<team key>-<number>``, never against a
    hard-coded prefix.
    """

    linear = config.get("linear")
    if not isinstance(linear, Mapping):
        raise AssertionError("configuration is validated before the Team binding is read")
    return str(linear["team_id"]), str(linear["team_key"])


def lifecycle_state_ids(config: Mapping[str, Any]) -> tuple[str, str] | None:
    """Return ``(completed_state_id, open_state_id)`` or ``None`` when unconfigured."""

    lifecycle = config.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        return None
    completed = lifecycle.get("completed_state_id")
    open_id = lifecycle.get("open_state_id")
    if not isinstance(completed, str) or not isinstance(open_id, str):
        return None
    return completed, open_id


# Safe defaults when the optional `hooks` section, or one of its keys, is
# absent. Installing the extension means you want Linear kept in sync, so a
# lifecycle-hook push runs and applies what it renders.
HOOKS_GATE_DEFAULTS: dict[str, bool] = {"lifecycle_enabled": True, "auto_apply": True}


def hooks_gate(config: Mapping[str, Any], key: str) -> bool:
    """Read one ``hooks.*`` gate, falling back to its documented default."""

    hooks = config.get("hooks")
    if isinstance(hooks, Mapping):
        value = hooks.get(key)
        if isinstance(value, bool):
            return value
    return HOOKS_GATE_DEFAULTS[key]


def repository_binding(config: dict[str, Any]) -> RepositoryBinding:
    repository = config["repository"]
    return RepositoryBinding(
        slug=repository["slug"],
        project_label_group_id=repository["project_label_group_id"],
        project_label_id=repository["project_label_id"],
        project_label_name=repository["project_label"],
        project_view_id=repository["project_view_id"],
        issue_view_id=repository["issue_view_id"],
    )
