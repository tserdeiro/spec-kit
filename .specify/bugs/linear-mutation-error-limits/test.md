# Bug Verification: `userPresentableMessage` surfaces in GraphQL error diagnostics

- **Slug**: linear-mutation-error-limits
- **Tested**: 2026-08-30
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

Both new tests pass and the full package suite is green with no regressions. The original end-to-end reproduction (a real `INVALID_INPUT` from Linear's API) was not exercised — it needs a live workspace and would mutate Linear — so the verification rests on a unit test that replays the exact response shape the reporter confirmed by instrumentation.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | Live `push --apply` against Linear with an over-limit title | skipped | Needs a Linear workspace and mutates it; also moot at HEAD — titles are clipped client-side since `d5a9277`, so this input can no longer reach the API |
| Automated equivalent | `uv run pytest tests/unit/test_linear_client.py::LinearClientTests::test_graphql_error_prefers_user_presentable_message_over_generic_message -v` | pass | Replays the confirmed response shape: generic `message` + `extensions.userPresentableMessage` → actionable text in `linear_graphql_message` |
| New / updated tests | Both new tests, `-v` | pass | 2 passed; redaction test also green |
| Regression suite | `cd packages/spec-kit-linear && uv run pytest tests -q` | pass | 380 passed, 176 subtests passed |
| Lint / type-check | — | not-run | Package configures no ruff/mypy/pyright |

## Output Excerpts

```
test_graphql_error_prefers_user_presentable_message_over_generic_message PASSED
test_graphql_error_redacts_secrets_in_user_presentable_message PASSED
380 passed, 176 subtests passed in 6.91s
```

## Residual Risks

- Real Linear API path unverified end-to-end; the simulated response shape comes from the reporter's runtime instrumentation, so confidence is high.
- Consumer repos remain exposed until they refresh the vendored extension to a release containing this change (> v0.7.1).

## Recommendation

Close the bug at source level: the fix is pinned by unit tests against the confirmed response shape and the suite shows no regressions. "Partial" reflects only that the live-API reproduction was not re-run — impractical and, for the title-limit case, impossible at HEAD by design. Release the package and refresh `app-maker`'s vendored extension.
