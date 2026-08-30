# Bug Fix: `_graphql_error` drops Linear's actionable `userPresentableMessage`
- **Slug**: linear-mutation-error-limits
- **Fixed**: 2026-08-30
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary
Applied the assessment's preferred remediation: `_graphql_error` now prefers
`extensions.userPresentableMessage` over the generic top-level `message` when
building `linear_graphql_message` diagnostics, so `INVALID_INPUT` errors (e.g.
Linear's field-length validation) surface their actionable cause instead of
"Argument Validation Error".

## Changes

| File | Change | Notes |
| --- | --- | --- |
| `packages/spec-kit-linear/src/spec_kit_linear/linear_client.py` | `_graphql_error`: per error item, use `extensions.userPresentableMessage` when it is a non-empty string, else fall back to `item["message"]`; same `redact_text(text.strip()[:200])` treatment and 3-diagnostic cap as before | ~line 970 |
| `packages/spec-kit-linear/tests/unit/test_linear_client.py` | Added two tests next to `test_graphql_errors_with_http_success_are_sanitized_and_fail` | See below |

## Diff Highlights

```python
presentable = extensions.get("userPresentableMessage") if isinstance(extensions, dict) else None
# For INVALID_INPUT, `message` is typically the generic "Argument
# Validation Error"; the actionable text (e.g. "name must be shorter
# than or equal to 80 characters") lives in `userPresentableMessage`.
# Prefer it when present, since a bare code once cost a debugging
# session to recover the remediation. Redacted either way, because a
# server message can echo credentials or user content.
message = presentable if isinstance(presentable, str) and presentable.strip() else item.get("message")
if isinstance(message, str) and message.strip():
    messages.append(redact_text(message.strip()[:200]))
```

## Tests Added or Updated
- `test_graphql_error_prefers_user_presentable_message_over_generic_message`: error with `message="Argument Validation Error"` and `extensions.userPresentableMessage="name must be shorter than or equal to 80 characters."` → a `linear_graphql_message` diagnostic contains the presentable text.
- `test_graphql_error_redacts_secrets_in_user_presentable_message`: `userPresentableMessage="Bearer top-secret"` → the token appears in neither `str(error)` nor any diagnostic message.

## Local Verification

| Command | Result |
| --- | --- |
| `cd packages/spec-kit-linear && uv run pytest tests/unit/test_linear_client.py -v` | 13 passed, 6 subtests passed |
| `cd packages/spec-kit-linear && uv run pytest tests/unit -q` | 355 passed, 176 subtests passed |

## Deviations from Assessment
None.

## Follow-ups
- Consumer side per assessment: `app-maker` should refresh its vendored `.specify/extensions/linear/` to pick up this fix once released (out of scope for this repo).
