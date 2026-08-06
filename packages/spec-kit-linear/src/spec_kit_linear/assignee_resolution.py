"""Plan-time resolution of ``[@alias]`` task annotations to Linear user ids.

Doc "Campos administrados": "El assignee puede establecerse al crear un
`Txxx` Issue si existe una configuracion explicita. Despues de su creacion,
Linear es la autoridad para la asignacion." This module is the one place that
turns a `tasks.md` `[@alias]` annotation (parser.py) into a Linear user id,
via the committed `team.members` alias -> email mapping (config.py) and a
remote `users` lookup by email (linear_client.py). It never mutates Linear
and never runs for an existing task's reconcile -- only ``planner.py``'s
``issue.create`` branch ever consults its result.

Fail-closed per doc "Parsing de artefactos" and "Codigos de salida":

- an alias referenced from `tasks.md` that is not a key in `team.members` is
  a *configuration* problem (exit 3), naming the alias and its file/line;
- an email that resolves to zero or two-or-more Linear users is a *remote
  identity* problem (exit 6), since the extension cannot safely guess which
  account to assign.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .config import team_members
from .domain import DesiredState
from .errors import AppError, Diagnostic
from .linear_client import LinearClient


def resolve_task_assignees(
    client: LinearClient,
    config: Mapping[str, object],
    desired_states: Sequence[DesiredState],
) -> dict[str, str]:
    """Return ``{task.identity: linear_user_id}`` for every ``[@alias]``-annotated task.

    Aliases are resolved once per unique email even when several tasks (or
    several features in one ``--all`` invocation) share the same alias, so a
    repeated alias never issues a duplicate remote query.
    """

    members = team_members(config)
    resolved: dict[str, str] = {}
    email_to_user_id: dict[str, str] = {}
    for desired in desired_states:
        for task in desired.feature.tasks:
            alias = task.assignee_alias
            if alias is None:
                continue
            email = members.get(alias)
            if email is None:
                raise AppError(
                    f"task {task.identity} references unknown assignee alias '{alias}'",
                    code=3,
                    category="configuration",
                    diagnostics=[
                        Diagnostic(
                            "task_assignee_alias_unknown",
                            f"add '{alias}' to 'team.members' in the shared configuration, or remove the [@{alias}] marker",
                            task.source.path,
                            task.source.line,
                        )
                    ],
                )
            if email not in email_to_user_id:
                email_to_user_id[email] = _resolve_single_user(client, alias, email)
            resolved[task.identity] = email_to_user_id[email]
    return resolved


def _resolve_single_user(client: LinearClient, alias: str, email: str) -> str:
    matches = client.find_users_by_email(email)
    if len(matches) != 1:
        raise AppError(
            f"assignee alias '{alias}' does not resolve to exactly one Linear user",
            code=6,
            category="remote_identity",
            diagnostics=[
                Diagnostic(
                    "task_assignee_email_ambiguous",
                    f"'team.members.{alias}' matched {len(matches)} Linear user(s); it must match exactly one",
                )
            ],
        )
    return matches[0].id
