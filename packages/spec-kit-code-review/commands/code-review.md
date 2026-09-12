---
name: speckit.code-review
description: Review the pending diff, or a pull-request candidate; publish only with an explicit flag.
---

# Spec Kit code review

One command. It detects what to review:

- **no argument** — the pending diff of the working tree (staged, unstaged and
  untracked). Advisory: there is no immutable candidate and no publishable
  verdict.
- **a pull request** — the anchored candidate `(merge_base, head_commit)`, with
  an optional `--publish`.

```bash
CR=".specify/extensions/code-review/scripts/bash/run.sh"
```

## Reviewing the working tree

```bash
bash "$CR" review
```

It prints the path of an advisory **review packet**. Read that packet in full,
review the code it describes, and report the findings to the user. Nothing is
written inside the repository and no session is opened.

## Reviewing a pull request

Run these two invocations in order; they are one review, and the user sees one
command.

```bash
# 1. resolve the candidate, materialize it, and write the packet
bash "$CR" review 128 --json

# 2. close the review with the findings you produced
bash "$CR" review --findings <session-path>/findings.json --session <session-path>
```

Step 1 prints `session.path` and `packet` in its JSON. Read the packet at
`<session-path>/review-packet.md`, write
`<session-path>/findings.json`, then run step 2. Findings outside that session
are refused because they cannot belong to this review.
**Always run step 2**, including when you found nothing: it is what withdraws
the temporary worktree and closes the session.

The candidate is materialized in a temporary worktree under the evidence root,
so the user's branch, index and untracked files are never touched. If step 2
never runs, the next review of the same candidate withdraws the orphan worktree
itself.

Step 2 refuses to normalize anything until it has proved it is closing the
review that was opened: the candidate is **re-resolved** and compared, and the
packet on disk is re-hashed against the digest step 1 recorded. Any discrepancy
is exit code 8 with nothing written. Then every finding is validated against the
candidate — one whose path or range does not exist is discarded as a
hallucination — anchorable findings become inline comments and the rest go to
the summary, and the verdict is derived.

The verdict is `no-blocking-findings`, `changes-requested` or `inconclusive` —
**never an approval**. `changes-requested` exits 1: the review ran correctly and
the candidate needs work. An `inconclusive` verdict names what it did not cover,
in the human render as well as in the JSON.

A task pull request — one whose base branch name starts with a number, such
as the feature branch `004-delivery-discipline` or a stacked task's own
`004-T007-…` — gets an automatic `blocking` finding for every touched
`protected_paths` entry (`specs/*/spec.md` and the constitution by default),
regardless of what the reviewing agent found. A pull request based on the
delivery trunk is exempt.

### findings.json

```json
{
  "findings": [
    {
      "path": "src/module.py",
      "start_line": 42,
      "end_line": 44,
      "severity": "blocking",
      "category": "correctness",
      "title": "…",
      "content": "…"
    }
  ]
}
```

Every candidate submission includes a source-validated
reading report. Copying a path or reference alone earns no coverage credit;
each receipt must hash the exact inclusive UTF-8 line range that was inspected
and include a short assessment tied to the reviewed scope:

```json
{
  "findings": [],
  "coverage": {
    "candidate_id": "<candidate_id>",
    "packet_sha256": "<packet_sha256>",
    "inventory_sha256": "<inventory_sha256>",
    "reads": [
      {
        "path": "specs/003-example/spec.md",
        "version": "<head_commit>",
        "start_line": 1,
        "end_line": 20,
        "sha256": "<sha256-of-the-exact-lines>",
        "assessment": "This range establishes the acceptance boundary.",
        "scope": "FR-001"
      }
    ]
  }
}
```

The session validates every receipt against the immutable candidate and frozen
inventory. Duplicate receipts are deduplicated and overlapping receipts are
unioned; they do not over-credit coverage. Missing, partial, or invalid
receipts leave unresolved gaps and make the review inconclusive while valid
findings remain available. A changed
candidate, packet, inventory, or configuration refuses closure before any
evidence is written. Reopen a completed session to submit corrected evidence.
Assessments are reviewer-reported evidence of inspected ranges, not proof of
comprehension. For pull requests, inspect the frozen intent source recorded in
the inventory using its exact version and retrieval information; later edits to
the live pull-request text do not replace that snapshot.

Severities: `blocking`, `major`, `minor`, `nit`, `info`. Categories:
`correctness`, `security`, `contract`, `delivery`, `tests`,
`maintainability`, `style` — any other value refuses the whole file. Cite
the exact lines that support each finding; anything that does not exist in
the candidate is discarded.

## Publishing

```bash
bash "$CR" review --findings <session-path>/findings.json --session <session-path> --publish
```

Publication is **always explicit** and only ever reaches GitHub through two
POSTs: creating a review with event `COMMENT` or `REQUEST_CHANGES`, and adding
the summary comment. Immediately before the first write the candidate is
re-resolved: a head or a merge base that moved is exit code 8 with nothing
published, because a published comment cannot be withdrawn.

`APPROVE` is unreachable from every combination of flags and configuration, and
so is merging. A second publication of the same candidate is refused rather than
duplicated. Approving and merging remain human decisions.
