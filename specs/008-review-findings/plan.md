# Implementation Plan: Correct review finding categories

**Feature directory**: `specs/008-review-findings`
**Spec**: [spec.md](spec.md)

## Summary

Generate category guidance from `findings.CATEGORIES`, then extend the existing
findings submission boundary with a preserved original and category-only
comparison. The reviewer edits `findings.json` and repeats the existing close
command; strict validation and session checks decide the result. Keep research,
data contracts, and validation here, following the resolved template.

## Technical context

- **Language/runtime**: Python 3.11+; existing Bash/PowerShell launchers.
- **Primary dependencies**: standard library only; existing Git, `gh`, and pinned
  OCR. Development tests use pytest 9.1.1. Sources: [manifest](../../packages/spec-kit-code-review/pyproject.toml),
  [lock](../../packages/spec-kit-code-review/uv.lock), [pins](../../versions.lock.yml).
- **Storage/state**: consumer-owned private review evidence, `session.json`,
  submitted findings, and a per-review-attempt correction directory.
- **Verification**: existing pytest fixtures, fake GitHub/OCR, golden packets,
  installed-consumer conformance, and `git diff --check`.
- **Target environment**: the package's existing consumer platforms and selected
  integrations; advisory review stays sessionless.
- **Constraints**: native review surface, current budgets and 2× forecast stop,
  upstream-managed baseline, and publication/human authority remain in force.
  This plan adds no dependency or public command/flag.

## Documentation

| Library or API | Version in use | Documentation |
| --- | --- | --- |
| Python standard library | 3.11+ | [JSON parsing](https://docs.python.org/3.11/library/json.html), [file creation and replacement](https://docs.python.org/3.11/library/os.html) |
| pytest | locked 9.1.1 | [Invocation](https://docs.pytest.org/en/stable/how-to/usage.html) |
| Review extension | current source | [Command contract](../../packages/spec-kit-code-review/commands/code-review.md), [findings](../../packages/spec-kit-code-review/src/spec_kit_code_review/findings.py), [sessions](../../packages/spec-kit-code-review/src/spec_kit_code_review/session.py) |

Official Python and pytest documentation was checked during planning. Verify
any additional API against its official source before implementation.

## Constitution check

| Principle or constraint | Pre-design | Post-design | Evidence |
| --- | --- | --- | --- |
| I. Compose pinned upstream | PASS | PASS | Authored extension and tests; pinned baseline preserved. |
| II. Preserve native surface | PASS | PASS | Existing two-step review and exact session submission. |
| III. Consumer-selected integrations | PASS | PASS | Common package and generated guidance; installed conformance is synthetic evidence. |
| IV. Durable repository truth | PASS | PASS | Original bytes and correction outcomes tied to the current review attempt. |
| V. Source/consumer boundary | PASS | PASS | Private consumer evidence; independently installed package. |
| VI. Traceable delivery units | PASS | PASS | Sequential task chain, FR/SC traces, whole-deliverable forecasts below 400 lines. |
| Sequential delivery and human gates | PASS | PASS | Entry 04 remains bounded; implementation follows entry 03, approval and remote gates stay explicit. |

## System boundaries and interfaces

| Boundary or interface | Owner | Change | Explicit non-goals |
| --- | --- | --- | --- |
| Catalog and validation | `findings.py` | Shared catalog; category-specific actionable diagnostics; strict preservation comparison | Category aliases or guessed mappings |
| Reviewer packet | `packet.py` | Render catalog from validator and point to the correction procedure | Review scope or Markdown coverage expansion |
| Submission and evidence | `cli.py`, `session.py`, new `finding_corrections.py` | Save original, validate proposed categories, record outcomes before closure | A new review engine or general retry workflow |
| Consumer guidance | `commands/code-review.md`, package README | Existing close command, evidence locations, and ambiguous-correction diagnosis | New publication authority |

## Technical decisions

### D1. Keep the validator's catalog authoritative

- **Decision**: Keep `CATEGORIES` in `findings.py`; render it from a local import
  inside the packet renderer because `findings.py` already imports packet
  escaping helpers. Static command guidance and README point to that generated
  catalog instead of owning another complete list.
- **Rationale**: `_require_enum()` already rejects categories, but the machine
  diagnostic separates the invalid value from the index/catalog in the outer
  error. The packet separately hardcodes the same values.
- **Trade-off**: Static documentation gives examples and the catalog location;
  the runtime packet is the exact version-specific list.

Introduce a category-specific diagnostic at the validator boundary, covering
unknown strings, non-strings, and a missing category. Put the one-based input
index, field, invalid/missing value, and allowed values together in the existing
`Diagnostic.message`; do not enlarge the shared error schema. The close caller
adds the actual same-session resubmission command and original-evidence path.
Keep other schema errors strict. Report category errors deterministically in
input order; repeated submission can expose another still-invalid field.

### D2. Preserve the original before offering correction

- **Decision**: Add a small `finding_corrections.py` module for capture,
  comparison, and correction records, called only from the existing phase-two
  close path. Read the submitted bytes once and derive parsing, digest, and
  preservation from those same bytes. Update the internal findings loader and
  its callers together; retain no alternate legacy loader path.
- **Rationale**: Today phase two keeps invalid sessions open, but the reviewer
  can overwrite the only input. `session.write_text()` redacts and rewrites
  text, so it cannot provide a byte-exact original snapshot.
- **Trade-off**: Correction needs a small amount of additional private evidence;
  unavailable evidence stops closure rather than weakening preservation.

After exact findings-path, open-session, configuration, candidate, packet, and
inventory checks, detect category errors in a structurally readable submission.
On its first category failure, durably capture `original.json` under
`finding-corrections/<attempt-id>/` and bind its digest to the session. This is
an exact binary snapshot with exclusive creation and existing 0700/0600
permissions, outside the repository. Verify an existing snapshot against its
recorded digest; a partial write or conflict produces an evidence diagnostic.
The tool never rewrites the reviewer's `findings.json`.

Each fresh session receives an opaque `findings_attempt_id`, generated once
when opened. Derive correction paths from that validated identifier, never from
finding content. Store records inside that directory, so reopening a candidate
at the same head creates a separate namespace and preserves prior originals.
Extend the existing session tests and golden scrubber for the new identifier.
A session predating this contract requires reopening; no migration or fallback.

### D3. Accept only category edits, then run the complete close pipeline

- **Decision**: Compare each attempted submission with the preserved original
  before normalization or generated protected-path findings. Match findings by
  original array position, preserve array length/order, and permit changes only
  to category fields whose original value was missing or outside `CATEGORIES`.
- **Rationale**: Comparing normalized findings would hide trimming, removal,
  reordering, defaults, and regenerated identifiers.
- **Trade-off**: A substantive review change needs a fresh review. Reformatting
  JSON and reordering object keys are harmless; changing types, field presence,
  array order, or any other values is not.

Use a type-sensitive structural comparison, including every optional finding
field and the full `coverage` envelope. Treat missing category separately from
an explicit null. Reject duplicate JSON object keys for this comparison so a
parser cannot hide changes behind the last occurrence. Preserve the normal
strict schema and size limit. An initially valid submission, including an empty
findings array, uses the normal pipeline without a correction snapshot.

A partial category correction is recorded and rejected until all categories
are valid. The reviewer chooses replacements from existing meaning; an
ambiguous mapping is reported explicitly and remains unresolved. There is no
runtime semantic guess or automatic downgrade. Once the allowed edits pass,
run full findings and coverage validation and existing verdict derivation.
If normalization would discard or truncate any submitted finding, reject the
correction and keep the session open; derived ordering, identifiers, anchoring,
and system-generated findings retain their existing meaning. Otherwise blocking
findings still yield `changes-requested`, and unresolved coverage/engine causes
retain the existing inconclusive verdict rather than a false green result.

### D4. Record validation separately from completion

- **Decision**: Persist a compact correction record for each distinct submitted
  byte digest: original/submitted digests, review identity, changed indices and
  old/new values, validation status, and diagnostic codes. Write a pending
  record before processing a correction, then its outcome before any close or
  publication. Use a temporary sibling plus atomic replacement for derived
  records and the session metadata that binds them; implement this in the
  existing session JSON writer so callers share one atomic write path. Keep
  the original snapshot exclusive and immutable.
- **Rationale**: A process interruption or failed evidence write must not look
  like an accepted correction. Existing session writers use direct writes, so
  their names are not evidence of atomicity.
- **Trade-off**: A pending record after interruption is evidence of an unfinished
  attempt. Repeating that digest reruns validation against current guards and
  completes the same record when its bindings are intact; it never assumes a
  previous success.

Record `rejected`, `validated`, or `pending` with a diagnostic/reason. `validated`
means the correction passed validation, not that the session closed, the
candidate passed review, or publication succeeded. Existing `session.json` and
publication evidence remain authoritative for those results. The final session
indexes the expected attempt-record digests and references the accepted
correction digest; every indexed record must exist and match its session
binding and recorded content digest before closure. A failed write between
record replacement and session-reference update leaves an explicit evidence
mismatch: stop and reopen rather than reconstructing history. `findings_sha256`
continues to
identify the exact accepted submission. Rejected attempts create no normalized
findings, publication plan, or closed state. All freshness checks precede reuse;
evidence errors retain an open session. Preserve the current publication flag
handling, environment restoration, and already-closed-session rejection.

## Data and migration behavior

| Data | Contract |
| --- | --- |
| `session.json` | Fresh `findings_attempt_id`; current original digest, expected correction-record references, and accepted correction reference when applicable. Existing candidate/packet/inventory identities remain authoritative. |
| `finding-corrections/<attempt-id>/original.json` | First category-invalid submission, preserved byte-for-byte and never overwritten. |
| `finding-corrections/<attempt-id>/<submitted-sha256>.json` | Redacted derived record containing identity, changes, status, and diagnostics; repeated bytes reuse the same record. |
| `findings.json` | Reviewer-owned proposed result; the tool reads it without rewriting it. |
| Existing normalized/session/publication evidence | Produced only after allowed category edits and full validation; accepted input digest and correction reference remain traceable. |

Bind records to attempt ID, candidate ID, frozen configuration, packet and inventory digests. Compare
against the original snapshot's digest on every retry. Preserve old attempt
directories when `_clear_previous_review_outputs()` clears current outputs;
existing whole-session retention removes their history only with that session.
Old open sessions are reopened using the normal lifecycle, without interpreting
missing correction fields as evidence of a new-format session.

## Failure, retry, rollout, and rollback

- **Failure behavior**: Category/schema/preservation errors use exit 2 and leave
  the session open. Drift retains exit 8. Evidence-write failures retain the
  environment-error contract (exit 7), with no successful correction or closure.
- **Retry/idempotency**: Repeat the existing `review --findings ... --session ...`
  invocation after editing only invalid categories. Reuse packet/engine analysis;
  repeat validation and correspondence checks. Same digest, same record.
- **Rollout**: Deliver after reliability entry 03; current checkout provides the
  concrete seams and has feature 007. Entry 03's artifacts are absent here, so
  verify its delivery/order before starting implementation. Run installed
  conformance before separately authorized release/publication.
- **Rollback**: Restore the previous package and start a fresh review. Keep
  original and correction files as historical evidence; do not replay them as
  findings for another review attempt.

## Security and privacy

Keep the exact original local under private evidence permissions. Do not pass
it through redaction, commit it, or attach it to a remote review. Derived records,
invalid values, diagnostics, and output continue through existing redaction and
containment. Reject symlinks or paths escaping the attempt directory for both
snapshot and record writes. Check content identity before trusting old evidence;
conflicting or partial evidence writes fail closed. Findings never select paths,
execute commands, or grant permission to publish.

## Verification strategy

| Requirement or risk | Evidence | Command or review |
| --- | --- | --- |
| FR-001–FR-002, SC-001 | Catalog equality; unknown/missing/non-string diagnostics in human and JSON output | `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_findings.py packages/spec-kit-code-review/tests/unit/test_packet.py packages/spec-kit-code-review/tests/unit/test_golden_packet.py -q` |
| FR-003–FR-006, SC-002–SC-004 | Same-session correction, original bytes, blocking verdict, all non-category fields and coverage preserved | `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_finding_corrections.py packages/spec-kit-code-review/tests/unit/test_phase_two.py -q` |
| FR-004/FR-007, SC-003–SC-004 | Repeated attempts, drift, tampering, write failures, reopen isolation, private files | `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_session.py packages/spec-kit-code-review/tests/unit/test_finding_corrections.py packages/spec-kit-code-review/tests/unit/test_phase_two.py -q` |
| All FR/SC; consumer boundary | Installed rejection → correction → close, retained blocking finding, unchanged engine-call count, no remote writes | `bash packages/spec-kit-code-review/scripts/conformance/review.sh` |
| Regression | Package suite, existing goldens, and whitespace | `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests -q`; `git diff --check` |

New test paths are planned artifacts. Tests exercise actual closure with the
existing fake engine/GitHub fixtures and valid coverage receipts. Installed
conformance proves the installed package workflow; it is not a live agent run.

## Source layout

```text
packages/spec-kit-code-review/
  src/spec_kit_code_review/
    findings.py
    finding_corrections.py                 # new
    packet.py
    session.py
    cli.py
  commands/code-review.md
  README.md
  tests/unit/
    test_findings.py
    test_finding_corrections.py            # new
    test_phase_two.py
    test_session.py
    test_cli.py
    test_packet.py
    test_golden_packet.py
    test_golden_review.py
  tests/golden/                           # affected packet/session fixtures
  scripts/conformance/review.sh
```

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Repeat category lists in static prose | Copies drift and do not prove recovery. |
| Map unknown categories automatically | Meaning can be ambiguous; the reviewer owns classification. |
| Remove invalid findings or lower severity | Loses review work and can manufacture a green result. |
| Reopen the review for every category error | Repeats analysis without changing the candidate. |
| Compare only normalized findings | Normalization can hide destructive changes. |

## Product handoff

`ready-for-development` requires all rows to be complete. Analysis consistency is not technical approval.

| Gate | Evidence | Status |
| --- | --- | --- |
| Clean Spec Kit analysis | Artifact review: 7 FR + 4 SC covered by 4 tasks; zero unresolved inconsistencies. Final read-only pass verifies these counts. | complete |
| Technical approval of plan and tasks | Human review requested after artifact preparation | pending |
| Reviewed Linear dry-run and synchronization | Plan preview: one Project; task preview: one Project + four Issues. Review and authorized synchronization remain pending. | pending |
| Every executable task individually assignable and assigned | Task ledger provides delivery units; assignees remain a human decision | pending |
