"""Environment-only authentication loading for Linear read operations."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .errors import AppError, Diagnostic


API_KEY_ENV = "LINEAR_API_KEY"
OAUTH_TOKEN_ENV = "LINEAR_OAUTH_ACCESS_TOKEN"


@dataclass(frozen=True)
class Credentials:
    """An authorization header whose value must never be rendered publicly."""

    scheme: str
    authorization: str

    def headers(self) -> dict[str, str]:
        return {"Authorization": self.authorization}


def _value(environment: Mapping[str, str], name: str) -> str | None:
    value = environment.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def load_credentials(environment: Mapping[str, str] | None = None) -> Credentials:
    """Load exactly one supported credential source without persisting it."""

    values = os.environ if environment is None else environment
    api_key = _value(values, API_KEY_ENV)
    oauth_token = _value(values, OAUTH_TOKEN_ENV)
    if api_key and oauth_token:
        raise AppError(
            "configure exactly one Linear credential source",
            code=3,
            category="configuration",
            diagnostics=[Diagnostic("linear_credentials_ambiguous", f"set only {API_KEY_ENV} or {OAUTH_TOKEN_ENV}")],
        )
    if api_key:
        # Linear personal API keys use the raw value in Authorization.
        return Credentials(scheme="api_key", authorization=api_key)
    if oauth_token:
        return Credentials(scheme="oauth", authorization=f"Bearer {oauth_token}")
    raise AppError(
        "Linear credentials are required for an online read-only check",
        code=4,
        category="prerequisite",
        diagnostics=[Diagnostic("linear_credentials_missing", f"set {API_KEY_ENV} or {OAUTH_TOKEN_ENV}")],
    )
