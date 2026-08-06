from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


def copy_consumer_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory()
    source = Path(__file__).parents[1] / "fixtures" / "consumer"
    destination = Path(temporary.name) / "consumer"
    shutil.copytree(source, destination)
    return temporary, destination

def isolate_operator_global_env(case) -> None:
    """Point the operator-global env file at a nonexistent path for this test.

    Without this, a developer's real ~/.config/speckit-linear/env leaks into
    any test that invokes the CLI, silently turning offline-fallback tests
    into live-credential runs.
    """

    from spec_kit_linear import env_files

    original = env_files.OPERATOR_GLOBAL_ENV_PATH
    env_files.OPERATOR_GLOBAL_ENV_PATH = Path(tempfile.gettempdir()) / "speckit-linear-test-no-global-env"
    case.addCleanup(setattr, env_files, "OPERATOR_GLOBAL_ENV_PATH", original)
