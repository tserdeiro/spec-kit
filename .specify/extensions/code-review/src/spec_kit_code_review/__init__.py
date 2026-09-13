"""Read-only primitives for the Spec Kit Code Review extension."""

from pathlib import Path

__version__ = "0.6.0"

# The installed extension this process runs from (the directory holding
# ``extension.yml``): the evidence names it so nobody has to guess which copy
# reviewed.
EXTENSION_ROOT = Path(__file__).resolve().parents[2]


def runtime_identity() -> dict[str, str]:
    """The running extension's version and root, as the evidence records them."""

    return {"extension_version": __version__, "extension_root": str(EXTENSION_ROOT)}
