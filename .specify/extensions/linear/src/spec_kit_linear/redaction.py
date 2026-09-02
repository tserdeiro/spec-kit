"""Centralized secret redaction for all public diagnostics."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


REDACTED = "[REDACTED]"
SENSITIVE_HEADER_NAMES = frozenset({"authorization", "cookie", "proxy-authorization", "x-api-key"})
SENSITIVE_ENV_NAMES = frozenset({"linear_api_key", "linear_oauth_access_token"})

_AUTHORIZATION_VALUE = re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+")
_BEARER_VALUE = re.compile(r"(?i)(bearer\s+)[^\s,;]+")
_QUERY_SECRET = re.compile(r"(?i)([?&](?:api[_-]?key|token|secret|access[_-]?token)=[^&#\s]+)")


def redact_text(value: object) -> str:
    """Return safe text without credential-shaped values or secret query data."""

    text = str(value)
    text = _AUTHORIZATION_VALUE.sub(rf"\1{REDACTED}", text)
    text = _BEARER_VALUE.sub(rf"\1{REDACTED}", text)
    return _QUERY_SECRET.sub(lambda match: f"{match.group(1).split('=', 1)[0]}={REDACTED}", text)


def redact_headers(headers: Mapping[str, object]) -> dict[str, str]:
    """Copy HTTP headers while replacing every credential-bearing value."""

    return {
        str(key): REDACTED if str(key).lower() in SENSITIVE_HEADER_NAMES else redact_text(value)
        for key, value in headers.items()
    }


def redact_environment(values: Mapping[str, object]) -> dict[str, str]:
    """Copy only a safe representation of environment values for diagnostics."""

    return {
        str(key): REDACTED if str(key).lower() in SENSITIVE_ENV_NAMES else redact_text(value)
        for key, value in values.items()
    }


def redact_structure(value: Any) -> Any:
    """Recursively sanitize diagnostic-only structures without changing shape."""

    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if str(key).lower() in SENSITIVE_HEADER_NAMES | SENSITIVE_ENV_NAMES else redact_structure(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [redact_structure(item) for item in value]
    if isinstance(value, tuple):
        return [redact_structure(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
