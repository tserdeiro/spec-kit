# spec-kit-code-review remote acceptance — Etapa 7

**Status: PERFORMED. Date: 2026-08-02.** Run against an authorized pull request
on a throwaway repository the owner created for it, with the owner confirming
the publication after being shown the exact plan. The reviewed code is
synthetic — a small ledger with deliberately planted defects — which is why a
public throwaway repository was acceptable.

## Candidate

| | |
|---|---|
| Repository | `tserdeiro/code-review-test` |
| Pull request | `#1` — "Add transfers and the billing batch worker" |
| base / merge base | `169747172bbb71a02419ed49440ca402f44136ba` |
| head | `6b54723e60239da1de510e1944066bf0994f808e` |
| `candidate_id` | `5bd60597113886aa5f0b50408a0adf00ee5f82da712d88141e3fbb7e66466f3d` |
| `packet_sha256` | `9d40893dc4d98cf77c09f1cada226b653463589159fa249de9f854a57051f86d` |
| Engine | `ocr` v1.8.3, the pinned binary from the distribution's data root |
| Review | https://github.com/tserdeiro/code-review-test/pull/1#pullrequestreview-4839768090 |
| Summary comment | https://github.com/tserdeiro/code-review-test/pull/1#issuecomment-5160479355 |

## What was exercised

Phase 1 resolved the pull request to its real base and immutable head, chose
the **worktree** strategy because the consumer checkout was dirty, and produced
a 439-line packet whose untrusted regions — the engine's output and the
pull-request body — arrived inside containment fences carrying the session
suffix. The rule set was empty at the head commit and the repository has no
Spec Kit feature, so both degraded to warnings and the review continued: the
documented fail-open, observed rather than assumed.

The reviewing agent read the packet, ran the diff commands it prints, and
returned six findings. Phase 2 validated them against the head, anchored all
six inline, counted 29 executable lines against the 400 budget, and returned
`changes-requested` on three blocking findings.

## Result, verified against the GitHub API rather than the tool's own output

```text
review:    state=COMMENTED  body_len=458  commit_id=6b54723e6023
inline:    src/accounts.py:26 :31 :34     all commit_id=6b54723e6023
           src/worker.py:5 :17 :18        all commit_id=6b54723e6023
summary:   1 issue comment, 582 bytes, carrying its candidate marker
pull request: state=open  merged=false   APPROVED reviews: 0
remote operations: 6 — four reads, two writes
```

Every checkbox of the procedure below holds:

- **The review body rendered** — 458 bytes, not empty. The Stage 6 defect that
  would have made this exact call a 422 is fixed, and now proven against the
  real API rather than a fake that accepted anything.
- **The inline comments are anchored to the head the review read.** Every
  `commit_id` is the head commit, not whatever the pull request points at now —
  the other Stage 6 fix, also proven here for the first time.
- **One summary comment, exactly once, carrying its marker.**
- **The event was `COMMENT`**, because `--request-changes` was not passed.
  Zero `APPROVED` reviews.
- **Neither approved nor merged**; the pull request is still open.
- **Nothing else on the pull request was touched**, and only allowlisted
  operations ran.
- **The reviewing checkout is unchanged**: still on `add-transfers`, no tracked
  modification.
- **A second `--publish-from` of the same candidate was refused**, naming the
  existing summary comment and stating that it is never edited or deleted.

## Defects this run found in the extension itself

First contact with reality is the point of an acceptance run. It found three
that no test had caught:

1. **`run` rejected the correct pinned binary.** The platform-independent
   `version_string` prefix rule from the 2026-08-02 amendment had landed in
   `doctor` only; `run`'s engine admission and `install`'s binding report still
   compared for equality, so the pinned engine was called wrong by `install`
   and refused outright by `run`. The command was unusable. Fixed during this
   run by moving the rule beside the pin in `lockfile.py`, where every caller
   shares it.
2. **A consumer cannot verify the `ocr` digest at all.** The lock is looked up
   only at the consumer's root and the extension package ships none, so
   `ocr_pin_missing` is a permanent warning in the field and the plan's "verify
   the digest before every review run" never happens outside this monorepo.
   **Open.**
3. **A clean temporary worktree is not withdrawn when the session closes**,
   although the session records `environment_restored: true` and the contract
   requires removing it when `git status --porcelain` inside it is empty. It
   stays registered in the consumer's `.git`. **Open.**

Minor: the operation ledger in `publication-result.json` records each
operation's method but not its endpoint, so the audit trail says two writes
happened without saying what they wrote to.

## Procedure (to repeat on any candidate)

```bash
# 1. Phase 1: produce the packet and open the session
run.sh run <pr> --packet-only

# 2. Review the packet yourself, produce findings.json, and close the session
run.sh run --findings ./findings.json --session <evidence>/<repo>/<sha>/session.json

# 3. Inspect the publication plan BEFORE publishing anything
cat <evidence>/<repo>/<sha>/publication-plan.json

# 4. Publish, answering the prompt
run.sh run --publish-from <evidence>/<repo>/<sha>/session.json
```

## What to verify afterwards, on the pull request itself

- [x] the review body **rendered** — an empty body is a 422, not a blank review
- [x] the inline comments landed on the head the review read (`commit_id`)
- [x] the summary comment is present, exactly once, carrying its
      `speckit-code-review:summary:<candidate_id>` marker
- [x] the event is `COMMENT`, or `REQUEST_CHANGES` if it was asked for and
      authorized — **never** `APPROVE`
- [x] the pull request was **neither approved nor merged**
- [x] nothing else on the pull request was edited, resolved or deleted
- [x] the working tree of the reviewing checkout is unchanged
- [x] a second `--publish-from` of the same candidate is refused without
      `--republish`

## Cleanup

The synthetic repository is the owner's to delete; nothing here depends on it
surviving. The digests above identify the candidate independently of whether
the pull request still exists.

## Addendum — v0.2.0 re-acceptance (2026-08-03)

Run with the single `review` command on a fresh head (`80c48e6`) of the same
pull request. Phase 1 anchored the candidate and produced a 29,235-byte
packet; phase 2 validated 5 findings, anchored all 5 inline, counted 38
executable lines against the 400 budget, and published with `--publish`:
review `4848417626` (`COMMENTED`, commit_id `80c48e6`), one summary comment,
zero `APPROVED` reviews, pull request still open — verified against the
GitHub API. `REQUEST_CHANGES` degraded to `COMMENT` because the
authenticated user authored the pull request; the verdict was
`changes-requested`, exit 1. The engine resolved from the canonical pinned
path with no environment override.
