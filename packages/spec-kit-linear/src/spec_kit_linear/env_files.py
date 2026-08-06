"""Best-effort auto-loading of ``LINEAR_*``/``SPECKIT_LINEAR_*`` pairs from dedicated env files.

Doc "Variables de entorno": before reading credentials or any other
environment variable, load ``KEY=VALUE`` pairs from (a) ``.speckit-linear.env``
at the consumer repository root, then (b) the operator-global
``~/.config/speckit-linear/env``. Neither file is a generic ``.env``: a
consumer repository's own project ``.env`` is never read here. Mixing this
extension's values into a project's own ``.env`` would be confusing and
easy to leak into an unrelated process; a dedicated, gitignored filename
keeps the two concerns apart. Only keys with prefix ``LINEAR_`` or
``SPECKIT_LINEAR_`` are ever auto-loaded from either file; every other key
is silently ignored. The real process environment always wins: a key
already set there is never overridden by either file, and once (a) has set
a key, (b) does not override it either -- both rules use the same "first
source wins, never overwrite" idiom :mod:`spec_kit_linear.credentials` and
the credential loader already uses for its own
precedence. (b) alone is the common case for a single-workspace operator
(one `LINEAR_API_KEY` for everything); (a) exists for a multi-workspace
operator who needs a different Linear org per client repository. Values are
never included in any diagnostic or exception message, matching the
redaction guarantee the rest of this extension already provides for
credentials.

This is deliberately not a full ``.env`` parser: no shell interpolation, no
command substitution, no variable expansion, no multi-line values -- only
plain ``KEY=VALUE`` lines, optionally with a matching pair of surrounding
single or double quotes stripped. A malformed line is a diagnostic, never a
crash.
"""

from __future__ import annotations

import os
import re
from collections.abc import MutableMapping
from pathlib import Path

from .errors import Diagnostic


ALLOWED_PREFIXES = ("LINEAR_", "SPECKIT_LINEAR_")
REPO_ENV_FILENAME = ".speckit-linear.env"
OPERATOR_GLOBAL_ENV_PATH = Path.home() / ".config" / "speckit-linear" / "env"
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _parse_env_file(path: Path) -> tuple[dict[str, str], list[Diagnostic]]:
    values: dict[str, str] = {}
    diagnostics: list[Diagnostic] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values, diagnostics
    except (OSError, UnicodeDecodeError):
        diagnostics.append(Diagnostic("env_file_unreadable", "could not read this env file", str(path), severity="warning"))
        return values, diagnostics

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            diagnostics.append(Diagnostic("env_file_malformed", "expected KEY=VALUE", str(path), line_number, severity="warning"))
            continue
        key, _, raw_value = line.partition("=")
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            diagnostics.append(Diagnostic("env_file_malformed", "invalid environment variable name", str(path), line_number, severity="warning"))
            continue
        if not key.startswith(ALLOWED_PREFIXES):
            # Silently ignored by design: only LINEAR_/SPECKIT_LINEAR_ keys
            # are ever auto-loaded from either file.
            continue
        values[key] = _strip_quotes(raw_value.strip())
    return values, diagnostics


def load_dotenv_files(root: Path, environment: MutableMapping[str, str] | None = None) -> list[Diagnostic]:
    """Load env-file overrides into ``environment`` (defaults to ``os.environ``).

    Reads, in precedence order, ``<root>/.speckit-linear.env`` (per-repo
    override) then ``~/.config/speckit-linear/env`` (operator-global
    default). Never overrides a key already present, in either file or in
    the real environment. Returns diagnostics for malformed lines and
    unreadable files; the returned list is empty on the common path
    (neither file exists, or every line was well-formed).
    """

    target = os.environ if environment is None else environment
    diagnostics: list[Diagnostic] = []
    for path in (root / REPO_ENV_FILENAME, OPERATOR_GLOBAL_ENV_PATH):
        values, file_diagnostics = _parse_env_file(path)
        diagnostics.extend(file_diagnostics)
        for key, value in values.items():
            if key not in target:
                target[key] = value
    return diagnostics
