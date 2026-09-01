"""Snapshot loading of ``SPECKIT_CODE_REVIEW_*`` values from dedicated env files.

Doc "Variables de entorno": before any variable is read, values are loaded, in
precedence order, from (a) ``${XDG_CONFIG_HOME:-~/.config}/tserdeiro/spec-kit/env`` -- the
operator's own file, outside every repository, and therefore the trusted source
-- then (b) ``.speckit-code-review.env`` at the consumer root. The real process
environment always wins over both, and the first file to define a key wins over
the second. Only keys carrying the ``SPECKIT_CODE_REVIEW_`` prefix are ever
loaded; the consumer's own project ``.env`` is never read.

Three restrictions apply to the repository file, and they are the reason this
module returns a frozen snapshot instead of mutating ``os.environ``:

1. it is read once, from the operator's original ref, before any execution
   environment is prepared, and never re-read afterwards;
2. it is rejected outright (exit code 3) when it is tracked in the candidate's
   head commit -- a tooling env file versioned by the candidate is an attempt to
   control the reviewer's environment;
3. it can never define an executable path: ``SPECKIT_CODE_REVIEW_OCR_BIN`` and
   ``SPECKIT_CODE_REVIEW_GH_BIN`` coming from it are ignored with a warning.

Deliberately not a full ``.env`` parser: plain ``KEY=VALUE`` lines only, with a
matching pair of surrounding quotes stripped. No interpolation, no command
substitution, no multi-line values. A malformed line is a diagnostic, never a
crash, and no value is ever logged or included in a message.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import EXIT_CONFIGURATION, AppError, Diagnostic
from .paths import operator_env_path


ENV_PREFIX = "SPECKIT_CODE_REVIEW_"
REPO_ENV_FILENAME = ".speckit-code-review.env"
# An explicit override, not a frozen default: comparing a module attribute
# against a recomputed default made `XDG_CONFIG_HOME` unobservable in-process,
# which is exactly what a test of this wiring needs to observe. `None` means
# "resolve it from the environment"; the suite sets it to keep a developer's
# real file out of every test.
_OPERATOR_ENV_OVERRIDE: Path | None = None
OPERATOR_GLOBAL_ENV_PATH = operator_env_path()
EXECUTABLE_OVERRIDE_KEYS = ("SPECKIT_CODE_REVIEW_OCR_BIN", "SPECKIT_CODE_REVIEW_GH_BIN")
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class EnvSnapshot:
    """The frozen environment that governs a whole session."""

    values: dict[str, str]
    trusted: dict[str, str]
    diagnostics: tuple[Diagnostic, ...] = ()
    repo_file_present: bool = False

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def executable_override(self, key: str) -> str | None:
        """Executable overrides are honored only from the trusted sources."""

        if key not in EXECUTABLE_OVERRIDE_KEYS:
            raise ValueError(f"{key} is not an executable override key")
        return self.trusted.get(key)


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
        if not key.startswith(ENV_PREFIX):
            continue
        values[key] = _strip_quotes(raw_value.strip())
    return values, diagnostics


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def set_operator_env_override(path: Path | None) -> None:
    """Point the operator env file somewhere else, or back at the environment."""

    global _OPERATOR_ENV_OVERRIDE
    _OPERATOR_ENV_OVERRIDE = path


def operator_env_file(environment: Mapping[str, str] | None = None) -> Path:
    """The operator's env file for this invocation.

    Doc "Rutas por usuario": ``${XDG_CONFIG_HOME:-~/.config}/tserdeiro/spec-kit/env``,
    resolved per call so the variable is honoured, with an explicit override for
    the tests that must not read a developer's real file.
    """

    if _OPERATOR_ENV_OVERRIDE is not None:
        return _OPERATOR_ENV_OVERRIDE
    if OPERATOR_GLOBAL_ENV_PATH != operator_env_path():
        # A caller replaced the module attribute directly. Honoured for
        # compatibility, and reported by the same sentinel path.
        return OPERATOR_GLOBAL_ENV_PATH
    return operator_env_path(environment)


def load_env_files(root: Path, environment: Mapping[str, str] | None = None) -> EnvSnapshot:
    """Load the environment snapshot that governs this session.

    ``environment`` defaults to the real process environment and always wins.
    Nothing is written back into ``os.environ``: the snapshot is the single
    frozen source every later read goes through.
    """

    process_environment = dict(os.environ if environment is None else environment)
    values: dict[str, str] = {
        key: value for key, value in process_environment.items() if key.startswith(ENV_PREFIX)
    }
    trusted: dict[str, str] = dict(values)
    diagnostics: list[Diagnostic] = []

    operator_file = operator_env_file(process_environment)
    operator_values, operator_diagnostics = _parse_env_file(operator_file)
    diagnostics.extend(operator_diagnostics)
    for key, value in operator_values.items():
        if key not in values:
            values[key] = value
            trusted[key] = value

    repo_path = root / REPO_ENV_FILENAME
    repo_present = repo_path.is_file()
    repo_values, repo_diagnostics = _parse_env_file(repo_path)
    diagnostics.extend(repo_diagnostics)
    for key, value in repo_values.items():
        if key in EXECUTABLE_OVERRIDE_KEYS:
            diagnostics.append(
                Diagnostic(
                    "env_file_executable_override_ignored",
                    f"{key} from the repository env file is ignored; executable paths are honored only from the "
                    f"process environment or {operator_file}",
                    str(repo_path),
                    severity="warning",
                )
            )
            continue
        if key not in values:
            values[key] = value

    return EnvSnapshot(
        values=values,
        trusted=trusted,
        diagnostics=tuple(diagnostics),
        repo_file_present=repo_present,
    )


def assert_repo_env_not_tracked(path_is_tracked: bool, *, ref: str, root: Path) -> None:
    """Reject a session whose candidate tracks the repository env file.

    Doc "Restricciones del archivo de entorno del repositorio" rule 2: a
    tooling env file versioned by the candidate is not a legitimate
    configuration, it is an attempt to control the environment of whoever
    reviews it. Exit code 3, naming the file.
    """

    if not path_is_tracked:
        return
    raise AppError(
        f"{REPO_ENV_FILENAME} is tracked in {ref}",
        code=EXIT_CONFIGURATION,
        diagnostics=[
            Diagnostic(
                "repo_env_tracked",
                "a tooling environment file versioned by the candidate is rejected outright",
                str(root / REPO_ENV_FILENAME),
            )
        ],
    )
