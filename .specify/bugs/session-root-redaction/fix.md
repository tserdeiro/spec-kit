# Fix: session-root-redaction

`ReviewSession.repository_root` now expands the persisted, redacted value
(`Path(value).expanduser()`), exactly like `_prepared_from_session` does
since 0.2.2 for the environment paths. One property, every consumer fixed:
the phase-2 guard, the trusted pointer helpers, and any future reader.
No deviations from assessment.
