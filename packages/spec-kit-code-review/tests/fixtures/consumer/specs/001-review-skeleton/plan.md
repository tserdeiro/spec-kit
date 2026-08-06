# Implementation Plan: Review skeleton

## Decisions

- Configuration is read once, from the operator's original ref.
- External executables are resolved from PATH or trusted overrides only.

## Verification

- Unit tests over temporary Git repositories and fake external executables.
