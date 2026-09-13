#!/usr/bin/env python3
"""Internal bridge: read one JSON request on stdin and print one JSON result.

Usage: ``resolve_work_item.py [--root PATH] [--config PATH]``. The request is
one JSON object, ``{"issue_key": "TEAM-123"}``; the result contains native
Issue context and the exact suggested branch. This is an internal bridge, not
a public ``spec-kit-linear`` command.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from spec_kit_linear.errors import AppError, Diagnostic  # noqa: E402
from spec_kit_linear.work_item_resolution import resolve_work_item  # noqa: E402


def _error_payload(error: AppError) -> dict[str, object]:
    return {
        "code": error.code,
        "category": error.category,
        "status": "error",
        "message": str(error),
        "retryable": error.retryable,
        "resolution": None,
        "diagnostics": [item.as_dict() for item in error.diagnostics],
    }


def _failure(message: str, code: int, category: str, diagnostic: Diagnostic) -> AppError:
    return AppError(message, code=code, category=category, diagnostics=[diagnostic])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="internal configured Linear work-item resolver")
    parser.add_argument("--root", default=".")
    parser.add_argument("--config")
    args = parser.parse_args(argv)
    try:
        root = Path(args.root).expanduser().resolve(strict=True)
        raw = json.loads(sys.stdin.read())
        if not isinstance(raw, dict):
            raise _failure(
                "request must be a JSON object", 2, "usage",
                Diagnostic("work_item_input", "request must be a JSON object"),
            )
        result = resolve_work_item(raw, root=root, config_path=args.config)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except json.JSONDecodeError:
        failure = _failure(
            "request is not valid JSON", 2, "usage",
            Diagnostic("work_item_json", "stdin must contain one JSON object"),
        )
    except FileNotFoundError:
        failure = _failure(
            "repository root does not exist", 2, "usage",
            Diagnostic("root_missing", "--root must name an existing directory"),
        )
    except AppError as error:
        failure = error
    except Exception:
        failure = _failure(
            "configured work-item resolution failed unexpectedly", 9, "graphql",
            Diagnostic(
                "work_item_unexpected",
                "the resolver failed without exposing internal details",
            ),
        )
    print(json.dumps(_error_payload(failure), ensure_ascii=False, sort_keys=True))
    return failure.code


if __name__ == "__main__":
    raise SystemExit(main())
