"""The single path through which text reaches stdout, evidence, or GitHub."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable


REDACTED = "[redacted]"

# Doc "Credenciales": the catalog is deliberately GitHub- and model-provider
# shaped. It carries no Linear pattern: this extension never touches Linear,
# and importing another extension's catalog would only create a false sense of
# coverage.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bghp_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bgho_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bghu_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bghs_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    # Any bearer credential, however short, and however it is terminated: the
    # value class deliberately excludes whitespace, so a token followed by a
    # newline, a quote, or end-of-string is still fully covered.
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?im)^\s*Authorization:.*$"),
)

_SENSITIVE_ENV_NAME_RE = re.compile(r"(?:TOKEN|SECRET|PASSWORD|API_?KEY|CREDENTIAL)", re.IGNORECASE)
_GH_HOSTS_PATH = Path.home() / ".config" / "gh" / "hosts.yml"


def home_directory_pattern() -> re.Pattern[str] | None:
    """The operator's home directory, as a redactable literal.

    A home path is personal identity -- the user name is usually in it -- and it
    reaches JSON output legitimately (``rules --explain`` names the personal rule
    layer). It is replaced by ``~`` rather than by the redaction marker, because
    the *shape* of the path is the useful part and the name is not.
    """

    try:
        home = str(Path.home())
    except (OSError, RuntimeError):
        return None
    if not home or home in ("/", ""):
        return None
    return re.compile(re.escape(home) + r"(?=/|$)")


def redact_text(value: str, *, extra: Iterable[str] = ()) -> str:
    """Redact every catalogued credential shape and every supplied literal."""

    if not value:
        return value
    result = value
    for literal in sorted({item for item in extra if item}, key=len, reverse=True):
        result = result.replace(literal, REDACTED)
    for pattern in _PATTERNS:
        result = pattern.sub(REDACTED, result)
    home = home_directory_pattern()
    if home is not None:
        result = home.sub("~", result)
    return result


def redact_payload(payload: Any, *, extra: Iterable[str] = ()) -> Any:
    """Recursively redact every string inside a JSON-shaped payload."""

    literals = tuple(extra)
    if isinstance(payload, str):
        return redact_text(payload, extra=literals)
    if isinstance(payload, dict):
        return {key: redact_payload(value, extra=literals) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [redact_payload(item, extra=literals) for item in payload]
    return payload
