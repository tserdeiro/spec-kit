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
bash "$CR" review --findings ./findings.json --session <session-path>
```

Step 1 prints `session.path` and `packet` in its JSON. Read the packet at
`<session-path>/review-packet.md`, produce `findings.json`, then run step 2.
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

### findings.json

```json
[
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
```

Severities: `blocking`, `major`, `minor`, `nit`, `info`. Cite the exact lines
that support each finding; anything that does not exist in the candidate is
discarded.

## Publishing

```bash
bash "$CR" review --findings ./findings.json --session <session-path> --publish
```

Publication is **always explicit** and only ever reaches GitHub through two
POSTs: creating a review with event `COMMENT` or `REQUEST_CHANGES`, and adding
the summary comment. Immediately before the first write the candidate is
re-resolved: a head or a merge base that moved is exit code 8 with nothing
published, because a published comment cannot be withdrawn.

`APPROVE` is unreachable from every combination of flags and configuration, and
so is merging. A second publication of the same candidate is refused rather than
duplicated. Approving and merging remain human decisions.
