# Implementation Plan: Sufficient review context

**Feature directory**: `specs/007-review-context`
**Spec**: [spec.md](spec.md)

## Summary

Select complete task blocks and necessary shared sections before rendering
review context. Preserve source ranges, explain exclusions, and validate
reviewer-reported reading evidence when closing the existing review session.
Keep research, data contracts, and validation in this plan, as the resolved
template requires. Implementation follows the reliability round's entry 01.

## Technical context

- **Language/runtime**: Python 3.11+, existing Bash/PowerShell launchers.
- **Primary dependencies**: standard library only; Git, authenticated `gh`,
  pinned OCR 1.8.3; pytest 9.1.1 in the package lock. No new dependency.
  Sources: [manifest](../../packages/spec-kit-code-review/pyproject.toml),
  [lock](../../packages/spec-kit-code-review/uv.lock), [pins](../../versions.lock.yml).
- **Storage/state**: existing consumer-owned review evidence directory and
  session JSON; Git objects identify immutable source content.
- **Verification**: existing pytest fixtures, fake GitHub/OCR, isolated consumer
  conformance, golden packet checks, and `git diff --check`.
- **Target environment**: existing supported consumer environments and selected
  integrations. Advisory working-tree review remains sessionless.
- **Constraints**: preserve upstream 1.0.4, native commands, current review
  budget and 2× forecast stop. Every task includes its callers and tests within
  a forecast below 400 authored executable lines.

## Documentation

| Library or API | Version in use | Documentation |
| --- | --- | --- |
| Python standard library | 3.11+ | [hashlib](https://docs.python.org/3.11/library/hashlib.html), [dataclasses](https://docs.python.org/3.11/library/dataclasses.html) |
| Git | installed 2.50.1 | [git show](https://git-scm.com/docs/git-show) |
| GitHub CLI | existing installed CLI | [gh pr view JSON fields](https://cli.github.com/manual/gh_pr_view), including `headRefName` |
| pytest | locked 9.1.1 | [Invocation](https://docs.pytest.org/en/stable/how-to/usage.html) |

The read interfaces and hashing documentation were checked during planning.
Verify an undocumented interface against its official source before use.

## Constitution check

| Principle or constraint | Pre-design | Post-design | Evidence |
| --- | --- | --- | --- |
| I. Compose pinned upstream | PASS | PASS | Authored code-review package only; baseline assets and pin preserved. |
| II. Preserve native surface | PASS | PASS | Extend the existing findings document and packet; existing review invocations. |
| III. Consumer-selected integrations | PASS | PASS | Common Python and command guidance; no host-specific event dependency. |
| IV. Durable repository truth | PASS | PASS | Candidate-bound ranges and normalized evidence; feature selection unchanged. |
| V. Source/consumer boundary | PASS | PASS | Runtime ships in its own package; temporary consumer tests. |
| VI. Traceable delivery units | PASS | PASS | FR/SC mapping and sequential slices with complete-deliverable forecasts. |
| Sequential delivery and human gates | PASS | PASS | Entry 02 after 01; handoff gates below remain explicit. |

## System boundaries and interfaces

| Boundary or interface | Owner | Change | Explicit non-goals |
| --- | --- | --- | --- |
| Artifact interpretation | `sdd_context.py` | Complete task blocks with source ranges and traces | A shared cross-package parser framework |
| Review scope | new `review_context.py`, `github.py`, `cli.py` | Candidate-grounded task/feature/short-path selection | Branch naming or new public selectors |
| Packet | `packet.py` | Bounded selected excerpts, omissions, retrieval, coverage inventory | Markdown command review or OCR scope expansion |
| Reading evidence | new `coverage.py`, `findings.py`, `cli.py` | Source-validated receipts and unresolved gaps | Host telemetry or automatic proof of comprehension |
| Consumer guidance | `commands/code-review.md`, package README | Exact PR and advisory evidence workflow | New commands, flags, or publication authority |

## Technical decisions

### D1. Parse complete blocks with stable source ranges

- **Decision**: Extend `TaskEntry` with its inclusive source range, block text,
  traces, dependencies, changed-path hints, and completion evidence. Parse the
  canonical indented fields through the next real task or enclosing section
  boundary. Ignore task-like lines inside fenced examples while retaining
  fenced evidence inside real blocks. Preserve exact source text and line ends.
- **Rationale**: `parse_tasks()` currently extracts only checkbox titles, so
  the actual Delivery, Traces, and Boundaries fields never reach selection.
- **Trade-off**: Human prose is not a strict schema. Unsupported path shorthand,
  duplicate IDs, unresolved dependencies, and malformed blocks produce explicit
  selection gaps; they cannot silently establish complete coverage.

Reuse existing field names and compare fence behavior with the package's
fixtures and the authored Linear/preset parsers. Keep the code-review package
independently installable. Paths in protected-boundary clauses and evidence
commands are not changed-path claims. Plain title paths and explicit changed
boundaries are matching hints; preserve ambiguous clauses as shared context.
Wire parsed delivery and trace details into existing context/packet output in
the first slice so no parser-only feature is left without a caller.

### D2. Resolve scope using all candidate evidence

- **Decision**: Add `headRefName` to the existing `gh pr view` read and preserve
  the head branch in its snapshot. Combine validated feature/task branch
  identities, task-block changes between merge-base and head, and exact
  changed-path associations. Freeze the resulting scope and its evidence with
  the packet. Treat PR prose as supporting intent, never authority to narrow.
- **Rationale**: The current PR snapshot records only the base branch and the
  feature resolver can select an unrelated active feature for a bug or chore.
- **Trade-off**: Where association is uncertain, conservative whole-feature
  coverage costs more context. Remaining contradictions produce scope gaps.

| Observed scope | Required selection |
| --- | --- |
| Task branch with consistent candidate evidence | Its full task block plus every other task reached by changed paths or meaningful task-block changes. |
| Multiple affected tasks | Union of their complete blocks, requirements, shared constraints, and relevant dependency evidence. |
| Feature branch PR | Whole feature contract, plan, tasks, success criteria, and delivery evidence, irrespective of the last task touched. |
| Explicit refs without dependable task identity | Whole resolved feature; never guess a single task from one token. |
| Issue-key bug/chore branch | Short-path intent, rules, changed code, and available bug evidence; an unrelated active feature does not impose a ledger. |
| Ambiguous feature or unmatched changed paths | Explain the uncertainty; expand to whole-feature context when that resolves it, otherwise retain a scope gap. |

A task ID alone cannot exclude another affected task. Ledger edits are mapped
to real block ranges, not the path `tasks.md` as a match for every task.
Shared file matches include all matching tasks unless immutable block changes
and explicit boundaries disambiguate them. Scope conflicts cannot be cleared
by a read receipt. Reopening after corrected source evidence recomputes scope.

### D3. Select sources without rewriting their meaning

- **Decision**: `review_context.py` builds one deterministic inventory of
  required ranges, selected ranges, excluded ranges with reasons, and gaps.
  For task reviews retain the full selected task blocks, ledger delivery
  strategy and shared prose, related requirement/scenario sections, and shared
  plan constraints. Read local artifacts to locate ranges; only selected text
  enters the reviewer packet.
- **Rationale**: The cost being removed is injecting the entire growing ledger
  into agent context, not local parsing of that file.
- **Trade-off**: Unstructured spec/plan sections remain required in full when
  their relevance cannot be determined safely. No summarization substitutes for
  source text. Full-feature review may require additional reads.

Use FR/SC traces to select complete containing sections, including acceptance
scenarios, and keep all unscoped constraints, assumptions, and shared decisions.
A referenced but absent requirement is a gap. Direct dependency outcomes and
completion evidence are required; expand further only when referenced evidence
requires it, detect cycles, and never recursively inject unrelated history.
Every excluded span has a source location and reason. Record dependencies as
context, distinct from tasks whose implementation is in the reviewed candidate.
Constitution/rules and required bug artifacts retain their existing sources.

### D4. Enforce context limits before emission

- **Decision**: Keep 60,000-byte per-artifact and 400,000-byte total defaults.
  Allocate UTF-8 source content deterministically, accounting for the final
  rendered packet's metadata, escaping, and trusted instruction envelope.
  Multiple excerpts from one source share its per-artifact allowance. Reduce
  quoted content on line boundaries until the total fits; every removed
  required range remains a gap with an exact candidate retrieval action.
- **Rationale**: `assemble()` currently only warns about total overflow.
  Increasing limits would leave both incorrect scope and false reading claims.
- **Trade-off**: A smaller configured packet can require more external reads.
  Trusted instructions and source containment are preserved whole. A total
  limit too small for the minimal trusted envelope is an explicit configuration
  error before opening a session, with the required minimum reported.

Store the complete inventory beside the packet in the existing evidence
location; include its digest and a bounded coverage summary in the hashed
packet region so the inventory cannot itself defeat the limit. The complete
inventory lists required/excluded ranges and safely quoted retrieval commands.
Per-artifact limits govern source excerpts; the total governs rendered packet
bytes. Existing optional checklist/PR-body inclusion settings retain their
meaning and cannot exclude necessary intent or constraints without a gap.
Exact boundary, non-ASCII, escaping, and tiny-limit cases are tested.

### D5. Validate reading reports at the existing closure boundary

- **Decision**: Extend `findings.json` with `coverage`, bound to `candidate_id`
  and `packet_sha256`. Each reported read names source path/version, inclusive
  line range, SHA-256 of the exact inspected UTF-8 bytes, and a short assessment
  tied to task/requirement/scope. Check every range against immutable source
  bytes before crediting it; selected content is not automatically read.
- **Rationale**: The current loader returns only findings and discards other
  document claims. A path or hash copied from the packet is not a reading report.
- **Trade-off**: These are reviewer-reported, source-validated receipts, not
  observed runtime events or proof of understanding. A meaningful assessment
  is required, but humans judge its substance. No new host integration is needed.

Require a reading report for selected and additionally inspected source content.
A receipt credits exactly its full validated range, never a larger range from
one sample excerpt. Deduplicate identical receipts, union overlapping valid
ranges, and preserve gaps for wrong hashes, absent content, or incomplete reads.
Never turn invalid coverage into discarded findings. Missing/invalid coverage
keeps the review inconclusive while valid findings remain available; malformed
JSON retains the existing input-error behavior. Candidate, packet, inventory,
or configuration drift retains the existing refuse-before-write behavior.
Freeze PR intent bytes in the session if needed as a source; do not re-read
mutable PR prose to validate earlier receipts. Their snapshot digest remains
separate from immutable candidate identity and must match the reading report.

`coverage.py` validates and normalizes; `cli.py` orchestrates. Persist normalized
coverage with the findings source digest using existing atomic evidence writers.
A missing coverage inventory in an old session requires reopening with the new
version; do not add a compatibility path that infers coverage from old packets.

### D6. Derive completion from uncovered necessary content

- **Decision**: Replace blanket SDD-truncation causes with unresolved required
  ranges and scope gaps. Additional validated reads may cover omitted ranges;
  deliberate unrelated exclusions never become truncation causes. Preserve
  engine failures and every other existing inconclusive cause.
- **Rationale**: A task beyond the old cutoff can close when its actual context
  was reviewed; missing required material still prevents a conclusive result.
- **Trade-off**: A reviewer must obtain all needed content before phase two
  closes the session. Correct invalid JSON and retry an open session; after a
  completed inconclusive closure, open a fresh review to inspect more content.

Expose covered ranges and actionable remaining causes in session JSON and the
existing human/publication summary. Preserve blocking findings alongside an
inconclusive verdict; never conflate no findings with complete coverage.

### D7. Keep advisory review sessionless

- **Decision**: Use the same selection and inventory for working-tree packets,
  recording source hashes at capture. The host records its read ranges, hashes,
  and assessments in `coverage.json` beside that advisory packet using its
  existing file tools, then reports gaps to the user. Command guidance supplies
  the exact schema and requires comparing source hashes before reporting.
- **Rationale**: Advisory review currently has neither a session nor a phase-two
  CLI close; adding either would broaden the public lifecycle.
- **Trade-off**: Advisory evidence is host-reported and is not CLI-validated or
  publishable. A changed working-tree source requires a fresh advisory packet;
  its evidence cannot be reused in a later PR review.

## Data and migration behavior

| Data | Contract |
| --- | --- |
| Task block | Stable ID, exact source range/text, parsed traces/dependencies/delivery, changed-path hints, and parse gaps. |
| Context inventory | Scope kind/tasks/requirements and evidence; source versions; required, selected, excluded ranges; exclusion reasons; effective limits; gaps; canonical digest. |
| Read receipt | Source path/version, positive ordered inclusive range, exact content digest, scope-linked assessment; independently reported from inventory. |
| Coverage result | Candidate/packet/inventory identity, normalized reported reads, required ranges covered, unresolved causes, findings source digest. |
| Advisory evidence | Packet and working-source digests plus host-reported receipts; explicitly advisory, outside the repository. |

Source files keep their format. New sessions use the new evidence contract;
old sessions are reopened, not migrated. Existing findings remain immutable
input. Receipt validation reads only inventoried sources and candidate-owned
paths through existing readers, with no user-supplied command execution.

## Failure, retry, rollout, and rollback

- **Failure behavior**: Missing necessary content or reading evidence stays
  inconclusive; ambiguous scope stays visible. Drift rejects closure before
  normalization or publication. Impossible packet limits fail preflight.
- **Retry/idempotency**: Identical inputs yield the same canonical selection;
  duplicate receipts grant no extra coverage. Existing session close/publication
  guards remain authoritative. Additional reads resolve only their own gaps.
- **Rollout**: Deliver the task chain after entry 01, then publish the package
  through the separately authorized release workflow. Installed conformance
  precedes release; live acceptance remains entry 23.
- **Rollback**: Restore the previous package and open a fresh review. Preserve
  earlier evidence as historical records, never as coverage for a new candidate.

## Security and privacy

Preserve untrusted-content fences, escaping, canonical hashing, redaction,
private evidence permissions, and exact-session findings containment. Use
candidate Git objects for PR sources, not the operator's checkout. Treat read
assessments as untrusted text in every output. Reject path escapes, unsupported
source versions, and inventory tampering. No credentials or host telemetry
enter receipts; publication still requires its existing explicit authorization.

## Verification strategy

Commands run from the repository root after the relevant task is implemented.

| Requirement or risk | Evidence | Command or review |
| --- | --- | --- |
| FR-001–FR-004, SC-001/SC-002 | Complete blocks; all four scope kinds; shared requirements; ambiguous identities | `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_sdd_context.py packages/spec-kit-code-review/tests/unit/test_review_context.py -q` |
| FR-005, C-003 | UTF-8 limits, inventory, escaping, deterministic packet | `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_packet.py packages/spec-kit-code-review/tests/unit/test_packet_containment.py packages/spec-kit-code-review/tests/unit/test_golden_packet.py -q` |
| FR-006–FR-008, SC-003/SC-004 | Missing/wrong/overlapping/additional receipts; drift; engine causes; preserved findings | `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_coverage.py packages/spec-kit-code-review/tests/unit/test_phase_two.py packages/spec-kit-code-review/tests/unit/test_findings.py -q` |
| Advisory authority and scope | Working-tree capture and guidance; no session/publication | `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_working_tree.py -q` plus command-guidance review |
| Package regressions | Entire unit suite, including candidate, session and publication regressions | `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit -q` |
| Installed consumer behavior | Large-ledger and full-feature reads through the installed extension with fake OCR | `bash packages/spec-kit-code-review/scripts/conformance/review.sh` |
| Artifact hygiene | Scoped changes without whitespace errors | `git diff --check` |

Planning baseline: existing `test_sdd_context.py`, `test_packet.py`, and
`test_phase_two.py` passed: 96 tests and 23 subtests. This verifies the current
starting point, not the planned behavior.

Use an early unrelated ledger region exceeding 60,000 bytes, a small late task,
a second task sharing a requirement, and a final-feature candidate. Compare
selection before/after unrelated ledger growth. Verify absent required content,
non-ASCII limits, inaccessible extra reads, wrong candidate receipts, invalid
assessment records, and reference-only submissions. Fake-tool conformance is
installed-asset evidence, not actual agent runtime acceptance.

## Source layout

Paths below are relative to `packages/spec-kit-code-review/`; new files are marked.

```text
src/spec_kit_code_review/
  sdd_context.py
  review_context.py       (new: scope and source selection)
  coverage.py             (new: read-receipt validation)
  github.py
  packet.py
  findings.py
  cli.py
commands/code-review.md
README.md
config/speckit-code-review.template.yml
scripts/conformance/review.sh
tests/unit/test_sdd_context.py
tests/unit/test_review_context.py  (new)
tests/unit/test_coverage.py        (new)
tests/unit/test_packet.py
tests/unit/test_packet_containment.py
tests/unit/test_golden_packet.py
tests/unit/test_golden_review.py
tests/unit/test_findings.py
tests/unit/test_phase_two.py
tests/unit/test_working_tree.py
tests/unit/test_candidate.py
tests/support/fake_gh.py
tests/conftest.py
tests/golden/
```

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Increase or disable packet limits | Hides the scale problem and does not establish coverage. |
| Include only the branch's task | Misses multi-task changes, shared requirements, and final feature review. |
| Treat every omitted byte as inconclusive | Confuses deliberate exclusion with a missing requirement. |
| Treat a path, packet hash, or no-findings result as proof of reading | None records inspection of the relevant source ranges. |
| Introduce a context-read CLI or host telemetry | Broadens the lifecycle and integration dependency beyond this bounded feature. |

## Product handoff

`ready-for-development` requires all rows complete. Analysis consistency is
not technical approval. The current authorization covers artifacts through
analysis and local phase commits.

| Gate | Evidence | Status |
| --- | --- | --- |
| Clean Spec Kit analysis | Run after task generation; report remains in the conversation because analyze is read-only. | pending |
| Technical approval of plan and tasks | Human review after analysis. | pending |
| Reviewed Linear dry-run and synchronization | After-plan preview succeeded: one `project.create` for feature 007; no writes applied. Repeat after tasks and review before synchronization. | pending |
| Every executable task individually assignable and assigned | Task IDs will provide delivery units; assignment remains a human action. | pending |
