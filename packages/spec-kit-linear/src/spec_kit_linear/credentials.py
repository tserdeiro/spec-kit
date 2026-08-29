"""Environment-only authentication loading for Linear read operations."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .env_files import REPO_ENV_FILENAME, credential_source
from .errors import AppError, Diagnostic


API_KEY_ENV = "LINEAR_API_KEY"
OAUTH_TOKEN_ENV = "LINEAR_OAUTH_ACCESS_TOKEN"


@dataclass(frozen=True)
class Credentials:
    """An authorization header whose value must never be rendered publicly."""

    scheme: str
    authorization: str
    source: str | None = None

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
    recorded = credential_source()
    source = recorded[1] if recorded is not None else None
    if api_key:
        # Linear personal API keys use the raw value in Authorization.
        return Credentials(scheme="api_key", authorization=api_key, source=source)
    if oauth_token:
        return Credentials(scheme="oauth", authorization=f"Bearer {oauth_token}", source=source)
    raise AppError(
        "Linear credentials are required for an online read-only check",
        code=4,
        category="prerequisite",
        diagnostics=[
            Diagnostic(
                "linear_credentials_missing",
                f"set {API_KEY_ENV} in {REPO_ENV_FILENAME} at the repository root "
                f"(or ~/.config/speckit-linear/env for every repo) — `doctor --fix` writes the template; "
                f"{OAUTH_TOKEN_ENV} is the OAuth alternative",
            )
        ],
    )
