---
name: speckit.code-review.completions
description: Print a bash or zsh completion script for the review CLI.
---

# Spec Kit code review completions

```bash
bash .specify/extensions/code-review/scripts/bash/run.sh completions bash
bash .specify/extensions/code-review/scripts/bash/run.sh completions zsh
```

It prints a completion script to stdout and writes nothing. The script is
generated from the CLI's own argument tree, so it can never drift from the real
surface.

To use it, with `spec-kit-code-review` resolving on `PATH` (for example an alias
to the launcher above):

```bash
eval "$(spec-kit-code-review completions bash)"
eval "$(spec-kit-code-review completions zsh)"
```
