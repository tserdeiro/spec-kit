"""Structured errors shared by the local-only CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Diagnostic:
    """A precise, safe-to-render validation diagnostic."""

    code: str
    message: str
    path: str | None = None
    line: int | None = None
    severity: str = "error"

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }
        if self.path is not None:
            result["path"] = self.path
        if self.line is not None:
            result["line"] = self.line
        return result


class AppError(Exception):
    """An expected error with the public exit-code contract attached."""

    def __init__(
        self,
        message: str,
        *,
        code: int,
        category: str,
        diagnostics: list[Diagnostic] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.category = category
        self.diagnostics = diagnostics or []
        self.retryable = retryable


def diagnostic_for_path(code: str, message: str, path: Path, line: int | None = None) -> Diagnostic:
    """Create a relative-friendly diagnostic from a local path."""

    return Diagnostic(code=code, message=message, path=str(path), line=line)
