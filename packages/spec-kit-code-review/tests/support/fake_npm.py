#!/usr/bin/env python3
"""A fake ``npm`` that materializes what a real ``npm install`` would leave.

It exists so ``doctor --fix`` can be tested end to end without a network, and so
the *argv* it is invoked with can be asserted: the install is the one command
this extension executes on the operator's behalf, and the shape of that command
is part of the contract.

State file (``npm-state.json`` beside this executable, or the path in
``SPECKIT_CODE_REVIEW_FAKE_NPM_STATE``)::

    {
      "platform_package": "ocr-darwin-arm64",
      "binary_source": "/path/to/fake_ocr.py",   # copied to the binary's place
      "binary_text": "#!/bin/sh\\nexit 0\\n",     # used when there is no source
      "binary_state": {...},                     # written as ocr-state.json beside it
      "skip_binary": false,                      # install "succeeds", nothing appears
      "exit_code": 0,
      "stderr": "",
      "record_invocations": "/path/to/log.txt"
    }
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
from pathlib import Path


STATE_ENV = "SPECKIT_CODE_REVIEW_FAKE_NPM_STATE"


def _state() -> dict:
    candidates = [os.environ.get(STATE_ENV), str(Path(__file__).resolve().parent / "npm-state.json")]
    for path in candidates:
        if not path:
            continue
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def _record(state: dict, argv: list[str]) -> None:
    destination = state.get("record_invocations")
    if not destination:
        return
    try:
        with open(destination, "a", encoding="utf-8") as handle:
            handle.write(" ".join(argv) + "\n")
    except OSError:
        pass


def _flag(argv: list[str], name: str) -> str | None:
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def main(argv: list[str]) -> int:
    state = _state()
    _record(state, argv)

    if argv[:1] != ["install"]:
        sys.stderr.write(f"fake npm: unsupported invocation: {' '.join(argv)}\n")
        return 1

    exit_code = int(state.get("exit_code", 0))
    if state.get("stderr"):
        sys.stderr.write(str(state["stderr"]) + "\n")
    if exit_code:
        return exit_code

    prefix = _flag(argv, "--prefix")
    if not prefix:
        sys.stderr.write("fake npm: no --prefix\n")
        return 1
    if state.get("skip_binary"):
        return 0

    package = state.get("platform_package") or "ocr-unknown"
    binary = Path(prefix) / "node_modules" / "@alibaba-group" / package / "bin" / "opencodereview"
    binary.parent.mkdir(parents=True, exist_ok=True)
    source = state.get("binary_source")
    if source:
        shutil.copyfile(source, binary)
    else:
        binary.write_text(state.get("binary_text") or "#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    binary_state = state.get("binary_state")
    if binary_state is not None:
        # `fake_ocr` reads its state from a sibling file, which is what makes it
        # work under the minimal environment the extension runs the engine in.
        (binary.parent / "ocr-state.json").write_text(json.dumps(binary_state), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
