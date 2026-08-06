"""In-package reader for ``versions.lock.yml``, including nested external tools.

Doc "Pin e integridad de OCR": the OCR pin is nested inside this extension's own
lock entry, under ``extensions.code-review.external_tools.open_code_review``.
There is no top-level ``tools:`` block, because OCR is a dependency *of this
extension*, not a component of the distribution.

This is a port of ``scripts/release/lockfile.py``, on purpose: the package never
imports tooling from the source repository at runtime.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .config import load_yaml_subset


EXTENSION_ID = "code-review"
EXTERNAL_TOOL_NAME = "open_code_review"
LOCK_FILENAME = "versions.lock.yml"
SELF_PIN_FILENAME = "engine.lock.yml"


@dataclass(frozen=True)
class ExternalToolPin:
    """One pinned external tool of an extension entry."""

    name: str
    values: dict[str, Any]

    @property
    def release_tag(self) -> str | None:
        return _text(self.values.get("release_tag"))

    @property
    def version_string(self) -> str | None:
        return _text(self.values.get("version_string"))

    @property
    def source(self) -> str | None:
        return _text(self.values.get("source"))

    @property
    def npm_package(self) -> str | None:
        return _text(self.values.get("npm_package"))

    @property
    def binaries(self) -> dict[str, str]:
        binaries = self.values.get("binaries")
        if not isinstance(binaries, dict):
            return {}
        return {str(key): str(value) for key, value in binaries.items()}

    def binary_digest(self, platform_key: str) -> str | None:
        return _text(self.binaries.get(platform_key))


@dataclass(frozen=True)
class ExtensionPin:
    """One ``extensions.<id>`` entry of the lock."""

    identifier: str
    values: dict[str, Any]

    @property
    def version(self) -> str | None:
        return _text(self.values.get("version"))

    @property
    def tag(self) -> str | None:
        return _text(self.values.get("tag"))

    @property
    def manifest_sha256(self) -> str | None:
        return _text(self.values.get("manifest_sha256"))

    def external_tool(self, name: str = EXTERNAL_TOOL_NAME) -> ExternalToolPin | None:
        tools = self.values.get("external_tools")
        if not isinstance(tools, dict):
            return None
        entry = tools.get(name)
        if not isinstance(entry, dict):
            return None
        return ExternalToolPin(name=name, values=dict(entry))


def lock_path(root: Path) -> Path:
    return root / LOCK_FILENAME


def self_pin_path() -> Path:
    """The pin file this extension ships, inside the package itself so it
    travels in the wheel the launcher's venv installs."""

    return Path(__file__).resolve().parent / SELF_PIN_FILENAME


def self_external_tool_pin(name: str = EXTERNAL_TOOL_NAME) -> ExternalToolPin | None:
    """The engine pin distributed inside the installed extension.

    A consumer repository has no ``versions.lock.yml``; this file travels in
    the release archive (covered by its subtree digest) and is the default
    pin. A consumer-root lock, when present, wins over it.
    """

    document = load_lock(self_pin_path())
    if not isinstance(document, Mapping):
        return None
    tools = document.get("external_tools")
    if not isinstance(tools, Mapping):
        return None
    entry = tools.get(name)
    if not isinstance(entry, Mapping):
        return None
    return ExternalToolPin(name=name, values=dict(entry))


def load_lock(path: Path) -> dict[str, Any] | None:
    """Best-effort read of a ``versions.lock.yml``-shaped file; ``None`` when absent or unreadable."""

    if not path.is_file():
        return None
    try:
        return load_yaml_subset(path)
    except Exception:  # noqa: BLE001 - a malformed lock is a diagnosis, never a crash
        return None


def extension_pin(lock: Mapping[str, Any] | None, identifier: str = EXTENSION_ID) -> ExtensionPin | None:
    if not isinstance(lock, Mapping):
        return None
    extensions = lock.get("extensions")
    if not isinstance(extensions, Mapping):
        return None
    entry = extensions.get(identifier)
    if not isinstance(entry, Mapping):
        return None
    return ExtensionPin(identifier=identifier, values=dict(entry))


def platform_key() -> str:
    """The ``<os>-<arch>`` key the lock uses for per-platform binary digests."""

    system = sys.platform
    if system.startswith("darwin"):
        operating_system = "darwin"
    elif system.startswith("linux"):
        operating_system = "linux"
    elif system.startswith("win"):
        operating_system = "windows"
    else:
        operating_system = system
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        architecture = "amd64"
    elif machine in {"arm64", "aarch64"}:
        architecture = "arm64"
    else:
        architecture = machine or "unknown"
    return f"{operating_system}-{architecture}"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def first_line(text: str) -> str:
    return (text or "").splitlines()[0].strip() if (text or "").strip() else ""


def version_matches_pin(observed: str, expected: str) -> bool:
    """Whether the installed engine is the pinned one.

    ``ocr --version`` prints the identity *and* the environment::

        open-code-review v1.8.3 (80a579466) darwin/arm64
        built at: 2026-07-31T09:24:52Z
        https://github.com/alibaba/open-code-review

    The pin is the platform-independent prefix -- name, version, commit -- and
    the check is that the observed first line **starts with** it. Comparing the
    whole output for equality makes the lock a per-machine value: a
    ``darwin/arm64`` string pinned in a shared file fails for every Linux user,
    blaming their correct installation. Per-platform integrity is what the
    ``binaries`` digest map is for.

    This lives beside the pin rather than inside any one command because every
    caller has to apply the same rule. It did not, once: the prefix rule landed
    in ``doctor`` while ``run``'s engine admission and ``install``'s binding
    report kept comparing for equality, so the pinned binary was reported as
    wrong by ``install`` and *rejected outright* by ``run`` -- found by the
    first end-to-end acceptance run, not by any test.
    """

    return first_line(observed).startswith(expected.strip())
