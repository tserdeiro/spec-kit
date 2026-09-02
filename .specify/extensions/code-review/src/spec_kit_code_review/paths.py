"""Where this distribution writes outside a repository, and nowhere else.

Doc "Rutas por usuario y ubicación de las herramientas externas". Everything the
distribution writes outside a repository lives under the ``tserdeiro/spec-kit``
namespace -- the lock's ``distribution.id`` -- across the three XDG roots, each
honouring its own variable:

``${XDG_CONFIG_HOME:-~/.config}/tserdeiro/spec-kit/env``
    The operator's configuration. The only trusted source of executable paths.
``${XDG_DATA_HOME:-~/.local/share}/tserdeiro/spec-kit/tools/<tool>/<version>/``
    Pinned external binaries, one directory per version, so several coexist and
    the path itself says which is which.
``${XDG_STATE_HOME:-~/.local/state}/tserdeiro/spec-kit/code-review/``
    Session evidence, ``0700``.

The separation is deliberate and is not formalism: the evidence carries diffs of
the code under review, potentially proprietary, and ``XDG_STATE_HOME`` exists
for what should not be synced or backed up along with a user's data.

The namespace matches ``distribution.id`` so a sibling extension can share these
roots later without a second convention.

Every function takes the environment as an argument rather than reading
``os.environ`` at import time: a path frozen at import cannot honour a variable,
and the session's environment snapshot is the single source every other read
already goes through.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping


DISTRIBUTION_NAMESPACE = ("tserdeiro", "spec-kit")
EXTENSION_DIRECTORY = "code-review"
TOOLS_DIRECTORY = "tools"
ENV_FILENAME = "env"

# The engine, and the package that provides it. Named here because the install
# command `doctor` prints is built from the same facts the lock pins.
OCR_TOOL_NAME = "ocr"
OCR_NPM_PACKAGE = "@alibaba-group/open-code-review"


def _root(environment: Mapping[str, str] | None, variable: str, *fallback: str) -> Path:
    """One XDG root, honouring its variable and falling back to the default.

    **A relative value is ignored**, as the XDG specification requires. It is not
    a stylistic point here: a relative ``XDG_CONFIG_HOME`` resolves against the
    current working directory, which during a review *is the repository under
    review* -- so the file this design calls the only trusted source of
    executable paths would be a file the candidate can write. Falling back to the
    default is the only safe reading of a value that cannot mean what it says.
    """

    source = os.environ if environment is None else environment
    value = (source.get(variable) or "").strip()
    if value:
        candidate = Path(value).expanduser()
        if candidate.is_absolute():
            return candidate.joinpath(*DISTRIBUTION_NAMESPACE)
    return Path.home().joinpath(*fallback).joinpath(*DISTRIBUTION_NAMESPACE)


def config_root(environment: Mapping[str, str] | None = None) -> Path:
    """``${XDG_CONFIG_HOME:-~/.config}/tserdeiro/spec-kit``."""

    return _root(environment, "XDG_CONFIG_HOME", ".config")


def data_root(environment: Mapping[str, str] | None = None) -> Path:
    """``${XDG_DATA_HOME:-~/.local/share}/tserdeiro/spec-kit``."""

    return _root(environment, "XDG_DATA_HOME", ".local", "share")


def state_root(environment: Mapping[str, str] | None = None) -> Path:
    """``${XDG_STATE_HOME:-~/.local/state}/tserdeiro/spec-kit``."""

    return _root(environment, "XDG_STATE_HOME", ".local", "state")


def operator_env_path(environment: Mapping[str, str] | None = None) -> Path:
    """The operator's env file: the only trusted source of executable paths."""

    return config_root(environment) / ENV_FILENAME


def evidence_root(environment: Mapping[str, str] | None = None) -> Path:
    """The default evidence root. The precedence chain above it is unchanged."""

    return state_root(environment) / EXTENSION_DIRECTORY


def tool_root(tool: str, version: str, environment: Mapping[str, str] | None = None) -> Path:
    """Where a pinned external tool of this version belongs.

    One directory per version: several can coexist, and an operator reading the
    path knows which one they are looking at without running it.
    """

    return data_root(environment) / TOOLS_DIRECTORY / tool / _version_segment(version)


# The npm package installs a JS **shim** at `node_modules/.bin/ocr`; the real Go
# binary -- the one the lock's digests are of -- lives in the platform package
# beside it. Pointing anything at the shim is caught by the digest check (which
# is the desired behaviour) but only after the operator has already installed
# and configured it, so every instruction names the platform binary directly.
OCR_SHIM_RELATIVE = ("node_modules", ".bin", "ocr")
OCR_BINARY_NAME = "opencodereview"


def platform_package(platform: str | None = None) -> str:
    """The npm platform package that carries the real binary for this machine."""

    key = platform or _platform_key()
    return f"ocr-{key}"


def _platform_key() -> str:
    """``<os>-<arch>`` as the engine's own packages name it."""

    import platform as platform_module

    system = platform_module.system().lower()
    machine = platform_module.machine().lower()
    architecture = {"x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    return f"{system}-{architecture}"


def tool_executable(
    tool: str,
    version: str,
    environment: Mapping[str, str] | None = None,
    *,
    platform: str | None = None,
) -> Path:
    """The **real** binary inside that directory, not the npm shim.

    `node_modules/.bin/ocr` is a JS wrapper whose digest is not the one the lock
    pins; the Go binary it delegates to is what `doctor` verifies. Naming the
    shim here would send every operator into a digest mismatch they would have
    to diagnose after the fact.
    """

    if tool != OCR_TOOL_NAME:
        return tool_root(tool, version, environment) / "node_modules" / ".bin" / tool
    return (
        tool_root(tool, version, environment)
        / "node_modules"
        / "@alibaba-group"
        / platform_package(platform)
        / "bin"
        / OCR_BINARY_NAME
    )


_SEMVER_TAG_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _version_segment(version: str) -> str:
    """A version as a path segment: no leading ``v``, nothing else changed."""

    text = (version or "unknown").strip()
    return text[1:] if text.startswith("v") and text[1:2].isdigit() else text


def npm_specifier(version: str, package: str) -> str | None:
    """``package@X.Y.Z`` for a release tag, or ``None`` when it is not one.

    The guard lives here rather than in one caller: a tag that is not a semantic
    version has no npm specifier, and building one anyway produces a command
    that fails in the operator's terminal -- as a *remediation*, which is the
    worst place for a command that cannot work.
    """

    text = (version or "").strip()
    if not _SEMVER_TAG_RE.match(text):
        return None
    return f"{package or OCR_NPM_PACKAGE}@{_version_segment(text)}"


def ocr_install_command(
    version: str,
    environment: Mapping[str, str] | None = None,
    *,
    package: str | None = None,
) -> str:
    """The same install as ``ocr_install_argv``, for a person to paste.

    Never a global install. A tool this extension pins must not outlive the
    extension's own uninstall on someone's machine, and a per-project install is
    not merely undesirable -- the executable guard refuses any binary that
    resolves inside the tree under review, which includes the consumer's
    ``node_modules`` and the extension's own directory under ``.specify/``.

    ``doctor --fix`` runs the argv form itself; this string is the manual
    alternative, and the reason both live here is that a remediation message and
    an executed command that disagree is exactly the failure this file prevents.
    """

    destination = tool_root(OCR_TOOL_NAME, version, environment)
    specifier = npm_specifier(version, package or OCR_NPM_PACKAGE)
    if specifier is None:
        return ""
    # `mkdir -p` and an empty `package.json` first: npm warns and ignores
    # `--save-exact` when the prefix has no manifest, so without them the
    # command a person pastes does not pin what it says it pins. The argv form
    # below prepares both from Python, for the same reason.
    return (
        f"mkdir -p {destination} && printf '{{}}' > {destination}/package.json && "
        f"npm install --prefix {destination} --save-exact {specifier}"
    )


def ocr_install_argv(
    npm: str,
    version: str,
    environment: Mapping[str, str] | None = None,
    *,
    package: str | None = None,
) -> list[str] | None:
    """That install as an argv list, or ``None`` when the tag is not a release.

    Argv, never a shell string: the destination and the specifier are built from
    the lock's own values, and a command line assembled by concatenation is the
    one place this package refuses to have.
    """

    specifier = npm_specifier(version, package or OCR_NPM_PACKAGE)
    if specifier is None:
        return None
    destination = tool_root(OCR_TOOL_NAME, version, environment)
    return [npm, "install", "--prefix", str(destination), "--save-exact", specifier]


def ocr_binary_hint(version: str, environment: Mapping[str, str] | None = None) -> str:
    """What to point `SPECKIT_CODE_REVIEW_OCR_BIN` at, and why not the shim."""

    return (
        f"{tool_executable(OCR_TOOL_NAME, version, environment)}  "
        f"(the real binary; `node_modules/.bin/ocr` is a JS shim whose digest is not the pinned one)"
    )


def ocr_uninstall_command(version: str, environment: Mapping[str, str] | None = None) -> str:
    """The exact command that removes it again, printed beside the install one."""

    return f"rm -rf {tool_root(OCR_TOOL_NAME, version, environment)}"


def resolved_roots(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """The three roots, resolved. `doctor` prints these, never the templates."""

    return {
        "config": str(config_root(environment)),
        "data": str(data_root(environment)),
        "state": str(state_root(environment)),
        "operator_env": str(operator_env_path(environment)),
        "evidence": str(evidence_root(environment)),
        "tools": str(data_root(environment) / TOOLS_DIRECTORY),
    }
