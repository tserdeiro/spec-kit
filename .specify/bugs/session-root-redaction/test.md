# Test: session-root-redaction

Reproduction: a phase-2 close whose session.json carries
`repository_root: ~/…` with `$HOME` pointing at the workspace — the exact
shape production writes for a repository under the home directory. Before
the fix it exits with `session_repository_mismatch`; after, the close
succeeds and withdraws the worktree. Added as a regression test next to
the 0.2.2 one (`RedactedSessionPathTests`), which shares the fake-HOME
technique. **Result: verified** (the new test fails on the unfixed
property and passes with the fix; full suite green).
