#!/usr/bin/env python3
"""Shim for the `pre_tool_use` runtime event; see commands/guard.md."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from spec_kit_code_review.cli import main

sys.exit(main(["guard"]))
