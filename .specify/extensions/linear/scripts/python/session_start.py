#!/usr/bin/env python3
"""Shim for the `session_start` runtime event; see commands/session-start.md."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from spec_kit_linear.cli import main

sys.exit(main(["session-start"]))
