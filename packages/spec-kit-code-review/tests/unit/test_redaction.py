from __future__ import annotations

import unittest

from spec_kit_code_review.redaction import REDACTED, redact_payload, redact_text


class RedactionCatalogTests(unittest.TestCase):
    def test_every_catalogued_pattern_is_redacted(self) -> None:
        samples = (
            "ghp_" + "a" * 36,
            "gho_" + "b" * 36,
            "ghu_" + "c" * 36,
            "ghs_" + "d" * 36,
            "github_pat_" + "e" * 40,
            "sk-" + "f" * 40,
        )
        for sample in samples:
            with self.subTest(sample=sample[:8]):
                self.assertEqual(redact_text(f"token is {sample} here"), f"token is {REDACTED} here")

    def test_bearer_and_authorization_header_are_redacted(self) -> None:
        self.assertNotIn("abcdefghijkl", redact_text("Authorization: Bearer abcdefghijkl"))
        self.assertEqual(redact_text("Bearer abcdefghijklmnop"), REDACTED)

    def test_the_catalog_carries_no_pattern_of_another_extension(self) -> None:
        # This extension never touches Linear; carrying its catalog would only
        # give a false sense of coverage.
        self.assertEqual(redact_text("lin_api_" + "a" * 40), "lin_api_" + "a" * 40)

    def test_literals_are_redacted_even_without_a_matching_pattern(self) -> None:
        self.assertEqual(redact_text("value=s3cret-literal", extra=("s3cret-literal",)), f"value={REDACTED}")

    def test_payloads_are_redacted_recursively(self) -> None:
        payload = {"message": "ghp_" + "a" * 36, "diagnostics": [{"message": "sk-" + "b" * 40, "line": 3}]}

        redacted = redact_payload(payload)

        self.assertEqual(redacted["message"], REDACTED)
        self.assertEqual(redacted["diagnostics"][0]["message"], REDACTED)
        self.assertEqual(redacted["diagnostics"][0]["line"], 3)


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
