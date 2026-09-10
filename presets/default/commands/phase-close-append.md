
## Phase close (tserdeiro/spec-kit)

This distribution closes every product phase silent and committed —
**where the hook and report rules above differ, these rules win**:

- **Hooks are acted on, never announced.** Wherever the core text above
  says to print an "Optional Hook" / "Optional Pre-Hook" block, print
  nothing. An optional hook whose own extension enables its event is
  executed silently — for `git.commit`, that gate is
  `auto_commit.<event>.enabled: true` in
  `.specify/extensions/git/git-config.yml`, regardless of
  `auto_commit.default`; every other optional hook is skipped silently.
  Mandatory hooks behave exactly as the core text says.
- **The resolved template rules the phase's own sections and files** —
  only what the resolved template defines, at the density of the
  precedent, never a heavier structure the core text's own generic
  example might suggest.
- **The phase ends committed.** After this command's own report, commit
  the feature's artifacts: stage only `specs/<feature-directory>/` — the
  active feature's directory, never anything outside it, however dirty
  the rest of the tree is — and commit with a `type(scope): subject`
  message in English naming the phase's artifact (e.g.
  `docs(specs): <feature> — implementation plan`). When those paths hold
  no changes, skip the commit silently. No reminders and no announcement
  beyond the commit appearing in the report's evidence, if this command
  reports any.
