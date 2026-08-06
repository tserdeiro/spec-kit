"""Structured errors carrying this extension's public exit-code contract."""

from __future__ import annotations

from dataclasses import dataclass


# Doc "Codigos de salida". The table is normative and shared by every command;
# it lives here rather than in cli.py so that a module raising an AppError
# never has to hardcode a bare integer, and so the CLI can render the category
# for a code without a second, drifting copy of the mapping.
EXIT_SUCCESS = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_CONFIGURATION = 3
EXIT_PREREQUISITE = 4
EXIT_AUTHENTICATION = 5
EXIT_CANDIDATE = 6
EXIT_ENVIRONMENT = 7
EXIT_DRIFT = 8
EXIT_ENGINE = 9
EXIT_PUBLICATION = 10
EXIT_INTERRUPTED = 130

EXIT_CATEGORIES: dict[int, str] = {
    EXIT_SUCCESS: "ok",
    EXIT_FINDINGS: "findings",
    EXIT_USAGE: "usage",
    EXIT_CONFIGURATION: "configuration",
    EXIT_PREREQUISITE: "prerequisite",
    EXIT_AUTHENTICATION: "authentication",
    EXIT_CANDIDATE: "candidate",
    EXIT_ENVIRONMENT: "environment",
    EXIT_DRIFT: "drift",
    EXIT_ENGINE: "engine",
    EXIT_PUBLICATION: "publication",
    EXIT_INTERRUPTED: "interrupted",
}

EXIT_DESCRIPTIONS: dict[int, str] = {
    EXIT_SUCCESS: "review completed, plan rendered, or action completed",
    EXIT_FINDINGS: "changes-requested verdict",
    EXIT_USAGE: "invalid usage or incompatible arguments",
    EXIT_CONFIGURATION: "invalid configuration, rules, or lock entry",
    EXIT_PREREQUISITE: "missing prerequisite or incompatible version",
    EXIT_AUTHENTICATION: "GitHub authentication or authorization failure",
    EXIT_CANDIDATE: "candidate not resolvable or ambiguous",
    EXIT_ENVIRONMENT: "review environment not preparable or not restorable",
    EXIT_DRIFT: "candidate or tracked content drifted during the session",
    EXIT_ENGINE: "review engine failure",
    EXIT_PUBLICATION: "publication or post-publication verification failure",
    EXIT_INTERRUPTED: "interrupted by a signal with the environment restored",
}


@dataclass(frozen=True)
class Diagnostic:
    """A precise, safe-to-render diagnostic."""

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
        category: str | None = None,
        diagnostics: list[Diagnostic] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.category = category or EXIT_CATEGORIES.get(code, "error")
        self.diagnostics = diagnostics or []
        self.retryable = retryable

