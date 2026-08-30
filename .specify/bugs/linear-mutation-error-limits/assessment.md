# Bug Assessment: Misleading mutation errors + missing Linear limit validation

- **Slug**: linear-mutation-error-limits
- **Created**: 2026-08-30
- **Source**: pasted text
- **Verdict**: valid — largely remediated at HEAD; one residual gap
- **Severity**: medium (original) / low (residual)

## Report (summarized)

Consumer repo (`app-maker`, vendored extension) ran `push --current --apply` on 2026-08-29: preview rendered 22 operations cleanly, apply failed exit 9 with `Linear returned GraphQL errors for this read query · linear_graphql: codes=INVALID_INPUT`. Real cause (confirmed by instrumenting the runtime): `projectCreate` rejected with `extensions.userPresentableMessage: "name must be shorter than or equal to 80 characters."` — the composed Project name (`NNN: ` + spec H1) was 85 chars. Two defects reported: (1) mutation errors reuse the read-query text and discard the actionable message; (2) no client-side validation of Linear limits (Project.name ≤ 80, Issue.title ≤ 255), so preview gives false confidence. Workaround: H1 shortened to keep the composed name at 75 chars.

## Symptom

Apply fails with a generic `INVALID_INPUT` labeled as a "read query" error, with no actionable cause; the preceding preview shows the same operations as executable.

## Reproduction

1. In a consumer repo with the linear extension vendored at < v0.7.0, create a feature whose spec H1 makes `NNN: ` + title exceed 80 chars.
2. `push --current` — preview renders all operations without warning.
3. `push --current --apply` — exits 9 with the misleading read-query message.

## Suspected Code Paths

- `packages/spec-kit-linear/src/spec_kit_linear/linear_client.py:970` (`_graphql_error`) — single error builder for reads and mutations; pre-fix it hardcoded "read query" and dropped `message`/`extensions.userPresentableMessage`.
- `packages/spec-kit-linear/src/spec_kit_linear/projection.py` — composes `{identifier}: {title}` / `{Txxx} {title}`; pre-fix had no limit awareness.
- `packages/spec-kit-linear/src/spec_kit_linear/mutation_executor.py:54` — mutation path funnels into the same `_decode_response`/`_graphql_error`.

## Root Cause Hypothesis

Confidence: high (confirmed by the reporter's instrumentation and by code reading). One shared error builder written for the read-only stage kept its read-query wording when mutations were added, and discarded the response fields where Linear puts the actionable cause. The projection composed titles with no knowledge of Linear's field limits, so invalid desired state survived until the API rejected it.

## Status at HEAD

Commit `d5a9277` (2026-08-29, released in `spec-kit-linear/v0.7.0`, current pin v0.7.1) already fixes both defects:

1. `_graphql_error` now says "for this request" (neutral for reads and mutations) and propagates up to 3 redacted error `message` texts as `linear_graphql_message` warning diagnostics. The reported `operation_kind`-in-error suggestion was not adopted; neutral wording removes the misleading claim, which suffices.
2. `project_feature` clips deterministically at the limits (`PROJECT_NAME_LIMIT = 80`, `ISSUE_TITLE_LIMIT = 255`) and emits a `linear_title_clipped` warning pointing at the source file/line of the offending title. Clipping is stronger than the suggested fail-fast: the desired state is always writable and reconciliation stays idempotent, while the warning still directs the author to shorten the H1. Warnings surface in both preview and apply (`cli.py:1007`, `cli.py:1147`).

**Residual gap**: `_graphql_error` reads only `item["message"]`. For Linear `INVALID_INPUT` validation errors the top-level `message` is typically the generic "Argument Validation Error"; the actionable text lives in `extensions.userPresentableMessage` — exactly where the reporter found it. Title-limit failures can no longer occur (clipped client-side), but any other future `INVALID_INPUT` would again surface without its actionable cause.

## Proposed Remediation

**Preferred**: in `_graphql_error`, also collect `extensions.userPresentableMessage` (string, non-empty), preferring it over the top-level `message` for the same error item; apply the identical redaction and 200-char truncation, keep the 3-diagnostic cap.

**Consumer side**: `app-maker` must refresh its vendored `.specify/extensions/linear/` to ≥ v0.7.1; the vendored copy predates the fix.

**Files likely to change**:
- `packages/spec-kit-linear/src/spec_kit_linear/linear_client.py`
- `packages/spec-kit-linear/tests/unit/test_linear_client.py`

**Tests to add or update**:
- GraphQL error with generic `message` ("Argument Validation Error") plus `extensions.userPresentableMessage` carrying the actionable text → diagnostic contains the presentable text, redacted.
- Presentable message containing a secret-like token → redacted, never in `str(error)`.

## Risks & Considerations

- `userPresentableMessage` is server-controlled text; it must pass through `redact_text` and the length cap like `message` already does (pattern exists, low risk).
- No API/behavior change beyond diagnostic content; exit codes unchanged.

## Open Questions

- None blocking. [NEEDS CLARIFICATION: none — reporter's instrumentation already confirmed the response shape.]
