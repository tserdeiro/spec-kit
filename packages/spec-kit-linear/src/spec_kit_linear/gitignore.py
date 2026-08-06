"""Non-destructive ``.gitignore`` entry management for consumer repositories.

The shared ``speckit-linear.yml`` is a committed artifact (it contains no
secrets -- see :data:`spec_kit_linear.config.ROOT_CONFIG_FILENAME`), so this
module never adds it to a consumer repository's ``.gitignore``. Only the
credential-bearing ``.speckit-linear.env`` (see
:mod:`spec_kit_linear.env_files`; never the consumer's own project ``.env``)
is ever added here.

Every edit is additive and idempotent: an existing ``.gitignore`` is read
verbatim, only the entries this module owns and that are missing are
appended (each on its own line, with a small identifying header comment the
first time), and every other line -- including any the operator wrote by
hand, in any order -- is preserved untouched. Nothing is ever removed,
reordered, or rewritten.
"""

from __future__ import annotations

from pathlib import Path

SECTION_HEADER = "# spec-kit-linear: local credentials"


def _covers(line: str, entry: str) -> bool:
    """A root-anchored variant (``/entry``) ignores the same root-level file."""

    return line == entry or line == "/" + entry


def has_entry(lines: set[str], entry: str) -> bool:
    """Whether any existing line already ignores ``entry``."""

    return any(_covers(line, entry) for line in lines)


def ensure_entries(path: Path, entries: tuple[str, ...]) -> list[str]:
    """Append any of ``entries`` missing from the ``.gitignore`` at ``path``.

    Returns the entries that were actually added (empty when every entry was
    already present, including when the file did not exist and nothing was
    requested). Does not write anything when there is nothing to add.
    """

    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    existing_lines = {line.strip() for line in existing_text.splitlines()}
    missing = [entry for entry in entries if not has_entry(existing_lines, entry)]
    if not missing:
        return []

    lines_to_append: list[str] = []
    if existing_text and not existing_text.endswith("\n"):
        lines_to_append.append("")
    if SECTION_HEADER not in existing_lines:
        lines_to_append.append(SECTION_HEADER)
    lines_to_append.extend(missing)

    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines_to_append) + "\n")
    return missing
