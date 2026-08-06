# Assessment: session-root-redaction

**Report**: WOR-31 — review phase 2 refuses every session in a repo under
the home directory ("the session was opened against ~/repositories/…; this
invocation is in ~/repositories/…" — the same path twice).
**Verdict**: real bug. `session.json` persists `repository_root`
home-redacted; `ReviewSession.repository_root` returns the literal-tilde
path and the phase-2 guard (`cli.py`, `session_repository_mismatch`)
resolves it relative to the CWD, so it never equals the real root when the
consumer lives under `$HOME`. Third member of the tilde-redaction family:
0.2.2 expanded `worktree_path`/`working_root`/`forbidden_roots` but not
this property. It never bit before because every test workspace and every
acceptance consumer lived under `/tmp`.
**Suspected paths**: `src/spec_kit_code_review/session.py` (the property is
the single reader all consumers share).
**Remediation**: expand the path in the property, mirroring the 0.2.2 fix.
