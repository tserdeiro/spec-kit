from __future__ import annotations

import unittest

from spec_kit_linear.credentials import load_credentials
from spec_kit_linear.errors import AppError
from spec_kit_linear.redaction import REDACTED, redact_environment, redact_headers, redact_text


class CredentialAndRedactionTests(unittest.TestCase):
    def test_api_key_and_oauth_headers_follow_linear_contracts(self) -> None:
        self.assertEqual(load_credentials({"LINEAR_API_KEY": "key-value"}).headers(), {"Authorization": "key-value"})
        self.assertEqual(
            load_credentials({"LINEAR_OAUTH_ACCESS_TOKEN": "token-value"}).headers(),
            {"Authorization": "Bearer token-value"},
        )

    def test_credentials_never_fall_back_to_config_or_allow_ambiguity(self) -> None:
        with self.assertRaises(AppError) as missing:
            load_credentials({})
        self.assertEqual(missing.exception.code, 4)
        with self.assertRaises(AppError) as ambiguous:
            load_credentials({"LINEAR_API_KEY": "one", "LINEAR_OAUTH_ACCESS_TOKEN": "two"})
        self.assertEqual(ambiguous.exception.code, 3)

    def test_redaction_removes_headers_environment_values_and_urls(self) -> None:
        self.assertEqual(redact_headers({"Authorization": "Bearer top-secret", "X-Trace": "trace"})["Authorization"], REDACTED)
        self.assertEqual(redact_environment({"LINEAR_API_KEY": "top-secret"})["LINEAR_API_KEY"], REDACTED)
        self.assertNotIn("top-secret", redact_text("Authorization: Bearer top-secret?token=still-secret"))
