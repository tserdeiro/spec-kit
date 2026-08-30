"""Small stdlib-only Linear GraphQL client with a guarded mutation boundary."""

from __future__ import annotations

import json
import random
import socket
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from http.client import RemoteDisconnected
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import __version__
from .credentials import Credentials
from .endpoint import DEFAULT_ENDPOINT, validate_endpoint
from .errors import AppError, Diagnostic
from .allowlist import assert_known_mutation
from .redaction import redact_text


# DEFAULT_ENDPOINT is re-exported from .endpoint, which owns endpoint
# resolution and validation outright (doc "Override de endpoint"); importing
# it here keeps the historical `from .linear_client import DEFAULT_ENDPOINT`
# spelling working for callers.
MAX_QUERY_BYTES = 32 * 1024
MAX_MUTATION_BYTES = 32 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_PAGE_SIZE = 50
MAX_PAGES = 100


class _RefuseRedirects(HTTPRedirectHandler):
    """Never follow a redirect away from the validated endpoint.

    Doc "Override de endpoint" makes ``endpoint.py`` the single place where a
    destination is resolved and validated. ``urlopen``'s default redirect
    handler quietly defeats that: on a 3xx it rebuilds the request against
    ``Location`` while copying every header except content-length/content-type
    -- ``Authorization`` included -- and it never re-validates the new host.
    An endpoint that answers ``302 Location: https://elsewhere.example`` would
    therefore send the operator's real Linear key to a host the validator
    never saw, which is precisely the redirection this override exists to make
    impossible.

    Returning ``None`` from :meth:`redirect_request` leaves the 3xx
    unhandled, so urllib's default error handler raises it as an
    :class:`HTTPError` that :meth:`LinearClient._decode_response` classifies
    explicitly. Refusing is deliberate rather than re-validating and
    following: Linear's real API does not redirect its GraphQL endpoint, so a
    redirect is either a misconfiguration or an attempt to move the
    credential, and both deserve a hard stop.
    """

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


_OPENER = build_opener(_RefuseRedirects)


def _open_without_redirects(request: Request, timeout: float | None = None) -> Any:
    """The default transport: `urlopen` minus its redirect following."""

    return _OPENER.open(request, timeout=timeout)


BINDING_QUERY = """
query BindingInspection(
  $teamId: String!
  $projectLabelGroupId: String!
  $projectLabelId: String!
  $projectViewId: String!
  $issueViewId: String!
) {
  viewer {
    organization { id }
  }
  team(id: $teamId) { id key name }
  projectLabelGroup: projectLabel(id: $projectLabelGroupId) { id name isGroup }
  projectLabel(id: $projectLabelId) { id name isGroup parent { id } }
  projectView: customView(id: $projectViewId) { id name type: modelName shared projectFilterData }
  issueView: customView(id: $issueViewId) { id name type: modelName shared filterData }
}
""".strip()

# `onboard` lifecycle sync: list every workflow state of a Team so the caller
# can pick the `completed`/`unstarted`-type state itself, breaking a tie by
# `position`.
WORKFLOW_STATES_BY_TEAM_QUERY = """
query WorkflowStatesByTeam($first: Int!, $after: String, $teamId: ID!) {
  workflowStates(
    first: $first
    after: $after
    filter: { team: { id: { eq: $teamId } } }
  ) {
    nodes { id name type position updatedAt }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()

# `onboard` PR-automation sync: the Team's existing git automation states, so
# the caller creates only the missing global mappings and never overwrites a
# human's different choice. Branch-scoped rules (targetBranch set) are read so
# they can be excluded from reconciliation, never touched.
GIT_AUTOMATION_STATES_BY_TEAM_QUERY = """
query GitAutomationStatesByTeam($teamId: String!) {
  team(id: $teamId) {
    gitAutomationStates {
      nodes {
        id
        event
        state { id name }
        targetBranch { id }
      }
    }
  }
}
""".strip()

# `onboard` degradation notice: whether the workspace has the GitHub
# integration connected at all (a one-time human OAuth step).
GITHUB_INTEGRATION_QUERY = """
query GithubIntegration($first: Int!, $after: String) {
  integrations(first: $first, after: $after) {
    nodes { id service }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()

PROJECT_LABELS_BY_NAME_QUERY = """
query ProjectLabelsByName($first: Int!, $after: String, $name: String!) {
  projectLabels(
    first: $first
    after: $after
    filter: { name: { eq: $name } }
  ) {
    nodes { id name isGroup updatedAt parent { id } }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()

# `onboard` read-only resolution. Unlike BINDING_QUERY (schema-conformed
# against the real API; see linear-remote-acceptance.md), these two have not
# yet been exercised against a live workspace and may need the same kind of
# conformance fix if the real schema disagrees.
VIEWER_ORGANIZATION_QUERY = """
query ViewerOrganization {
  viewer { organization { id } }
}
""".strip()

TEAM_BY_ID_QUERY = """
query TeamById($id: String!) {
  team(id: $id) { id key name }
}
""".strip()

TEAMS_BY_KEY_QUERY = """
query TeamsByKey($first: Int!, $after: String, $key: String!) {
  teams(first: $first, after: $after, filter: { key: { eq: $key } }) {
    nodes { id key name }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()

# "install --adopt-views"/"onboard" name-based Shared View adoption. Follows
# the same schema-conformance pattern BINDING_QUERY's customView fields
# already needed against the real API (see linear-remote-acceptance.md):
# `modelName` aliased to `type`, and a `String!` (not `ID!`) name filter
# argument, matching the other by-name connection queries above. Not yet
# exercised against a live workspace itself, the same caveat as
# VIEWER_ORGANIZATION_QUERY/TEAM_BY_ID_QUERY/TEAMS_BY_KEY_QUERY above.
SHARED_VIEWS_BY_NAME_QUERY = """
query SharedViewsByName($first: Int!, $after: String, $name: String!) {
  customViews(first: $first, after: $after, filter: { name: { eq: $name } }) {
    nodes { id name type: modelName shared updatedAt }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()

FEATURE_PROJECTS_QUERY = """
query FeatureProjects($first: Int!, $after: String, $projectLabelId: ID!) {
  projects(
    first: $first
    after: $after
    filter: { labels: { some: { id: { eq: $projectLabelId } } } }
  ) {
    nodes {
      id
      name
      description
      content
      updatedAt
      teams(first: 50) { nodes { id key } }
      labels(first: 50) { nodes { id name } }
      lead { id }
      members(first: 50) { nodes { id } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()

# "status" human-mode task table (contract "speckit.linear.status"): extends
# `assignee`/`state` with `displayName`/`name` so a consolidated per-feature
# row can show the assignee and workflow state without a second query.
# Follows the same schema-conformance caveat as the other nested-object
# fields above (`lead`/`members` on FEATURE_PROJECTS_QUERY, already
# schema-conformed via BINDING_QUERY's sibling shapes); not yet exercised
# against a live workspace itself.
#
PROJECT_ISSUES_QUERY = """
query FeatureIssues($first: Int!, $after: String, $projectId: ID!) {
  issues(
    first: $first
    after: $after
    filter: { project: { id: { eq: $projectId } } }
  ) {
    nodes {
      id
      identifier
      title
      description
      updatedAt
      url
      project { id }
      parent { id }
      assignee { id displayName }
      state { id name }
      labels(first: 50) { nodes { id name } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()


# Stage 5 (bugs and chores): resolve every observed Issue key to its real
# Issue in ONE batched read, never one query per key. The Team is addressed by
# the already-validated binding UUID and the keys by their numbers, which is
# exactly what a `<TEAM>-<number>` branch name encodes. Purely a read: queries
# never pass through the mutation allowlist, and nothing here can write.
WORK_ITEM_ISSUES_QUERY = """
query WorkItemIssues($first: Int!, $after: String, $teamId: ID!, $numbers: [Float!]!) {
  issues(
    first: $first
    after: $after
    filter: { team: { id: { eq: $teamId } }, number: { in: $numbers } }
  ) {
    nodes {
      id
      identifier
      title
      updatedAt
      url
      state { id name }
    }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()


@dataclass(frozen=True)
class RemoteWorkItem:
    """A bug or chore Issue this extension only ever reads and re-states."""

    id: str
    identifier: str
    title: str
    updated_at: str
    state_id: str | None = None
    state_name: str | None = None
    url: str = ""


@dataclass(frozen=True)
class RemoteBinding:
    workspace_id: str
    team_id: str
    team_key: str
    project_label_group_id: str
    project_label_group_name: str
    project_label_id: str
    project_label_name: str
    project_label_parent_id: str
    project_view_id: str
    project_view_type: str
    project_view_shared: bool
    issue_view_id: str
    issue_view_type: str
    issue_view_shared: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "team": {"id": self.team_id, "key": self.team_key},
            "project_label_group": {"id": self.project_label_group_id, "name": self.project_label_group_name},
            "project_label": {"id": self.project_label_id, "name": self.project_label_name, "parent_id": self.project_label_parent_id},
            "shared_views": [
                {"id": self.project_view_id, "kind": self.project_view_type, "shared": self.project_view_shared},
                {"id": self.issue_view_id, "kind": self.issue_view_type, "shared": self.issue_view_shared},
            ],
        }


@dataclass(frozen=True)
class RemoteTeamSummary:
    id: str
    key: str
    name: str


@dataclass(frozen=True)
class RemoteWorkflowState:
    id: str
    name: str
    type: str
    updated_at: str
    # `onboard` breaks a tie between same-type states by position.
    position: float = 0.0


@dataclass(frozen=True)
class RemoteGitAutomationState:
    """A Team PR-automation mapping; `onboard` only ever adds missing ones."""

    id: str
    event: str
    state_id: str | None
    state_name: str | None
    target_branch_id: str | None


@dataclass(frozen=True)
class RemoteProjectLabel:
    id: str
    name: str
    is_group: bool
    updated_at: str
    parent_id: str | None


@dataclass(frozen=True)
class RemoteSharedView:
    id: str
    name: str
    type: str
    shared: bool
    updated_at: str = ""


@dataclass(frozen=True)
class RemoteIssue:
    id: str
    identifier: str
    title: str
    description: str
    updated_at: str
    project_id: str
    parent_id: str | None
    assignee_id: str | None
    label_ids: tuple[str, ...]
    state_id: str | None = None
    # Defaulted for the same reason as RemoteWorkflowState.position/
    # RemoteSharedView.updated_at above: existing call sites that only ever
    # needed the ids keep constructing this unchanged. "status" (contract
    # "speckit.linear.status") is the first caller that reads these, via
    # PROJECT_ISSUES_QUERY's new `displayName`/`name` selections.
    assignee_name: str | None = None
    state_name: str | None = None
    # "start" (contract "speckit.linear.start") is the first caller that
    # reads this: the Issue's own permalink, read alongside `identifier`/
    # `assignee_name` so a developer gets a clickable link without a second
    # query. Read defensively (`_optional_string`, defaults to "") rather
    # than required, since the small fake GraphQL server used by existing
    # tests never populated a `url` field before this and should not have to.
    url: str = ""


@dataclass(frozen=True)
class RemoteProject:
    id: str
    name: str
    description: str
    updated_at: str
    team_ids: tuple[str, ...]
    label_ids: tuple[str, ...]
    issues: tuple[RemoteIssue, ...]
    lead_id: str | None = None
    member_ids: tuple[str, ...] = ()
    # The project overview document. Defaulted for the same reason as
    # lead_id/member_ids above: existing call sites that predate the
    # summary-in-content-block feature keep constructing this unchanged.
    content: str = ""


class LinearClient:
    """Bounded GraphQL transport; writes require a known allowlisted kind.

    Planning and application own their separate phase checks.  This additional
    client guard prevents an arbitrary caller from posting a GraphQL mutation.
    """

    def __init__(
        self,
        credentials: Credentials,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        opener: Callable[..., Any] = _open_without_redirects,
        sleeper: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self.credentials = credentials
        self.endpoint = _validate_endpoint(endpoint)
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self._opener = opener
        self._sleeper = sleeper
        self._jitter = jitter

    def query(self, document: str, variables: Mapping[str, object] | None = None) -> dict[str, object]:
        """Execute one bounded read query and reject every other document form."""

        normalized = document.lstrip()
        if not normalized.startswith("query "):
            raise ValueError("LinearClient accepts only named read queries")
        if len(document.encode("utf-8")) > MAX_QUERY_BYTES:
            raise ValueError("GraphQL query exceeds the bounded read-query size")
        request_id = str(uuid.uuid4())
        payload = json.dumps({"query": document, "variables": dict(variables or {})}, separators=(",", ":")).encode("utf-8")
        last_error: AppError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._execute_once(payload, request_id)
            except AppError as error:
                last_error = error
                if not error.retryable or attempt == self.max_attempts:
                    raise
                self._sleeper(self._retry_delay(error, attempt))
        assert last_error is not None
        raise last_error

    def mutation(
        self,
        document: str,
        variables: Mapping[str, object] | None = None,
        *,
        operation_kind: str,
    ) -> dict[str, object]:
        """Run exactly one allowlisted named mutation, with no blind retry.

        If the connection fails after bytes were sent, only the reconciler may
        decide recovery by re-reading the bridge identity.  Retrying here could
        duplicate a Feature Project or Issue.
        """

        assert_known_mutation(operation_kind)
        normalized = document.lstrip()
        if not normalized.startswith("mutation "):
            raise ValueError("LinearClient mutations must use a named mutation document")
        if len(document.encode("utf-8")) > MAX_MUTATION_BYTES:
            raise ValueError("GraphQL mutation exceeds the bounded mutation size")
        request_id = str(uuid.uuid4())
        payload = json.dumps({"query": document, "variables": dict(variables or {})}, separators=(",", ":")).encode("utf-8")
        return self._execute_once(payload, request_id)

    def connection(
        self,
        document: str,
        *,
        root_key: str,
        variables: Mapping[str, object],
        page_size: int = MAX_PAGE_SIZE,
    ) -> list[dict[str, object]]:
        """Read every page of a Relay connection with explicit safety limits."""

        if page_size < 1 or page_size > MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be within 1..{MAX_PAGE_SIZE}")
        cursor: str | None = None
        seen_cursors: set[str] = set()
        nodes: list[dict[str, object]] = []
        for _ in range(MAX_PAGES):
            page_variables = {**variables, "first": page_size, "after": cursor}
            data = self.query(document, page_variables)
            connection = _required_mapping(data, root_key, request_id=None)
            raw_nodes = connection.get("nodes")
            if not isinstance(raw_nodes, list) or not all(isinstance(node, dict) for node in raw_nodes):
                raise _schema_error("connection_nodes", f"Linear response '{root_key}.nodes' must be a list of objects")
            nodes.extend(raw_nodes)
            page_info = _required_mapping(connection, "pageInfo", request_id=None)
            has_next = page_info.get("hasNextPage")
            end_cursor = page_info.get("endCursor")
            if not isinstance(has_next, bool):
                raise _schema_error("connection_page_info", f"Linear response '{root_key}.pageInfo.hasNextPage' must be boolean")
            if not has_next:
                return nodes
            if not isinstance(end_cursor, str) or not end_cursor:
                raise _schema_error("connection_cursor", f"Linear response '{root_key}.pageInfo.endCursor' is required when another page exists")
            if end_cursor in seen_cursors:
                raise _schema_error("connection_cursor_loop", "Linear pagination returned a repeated cursor")
            seen_cursors.add(end_cursor)
            cursor = end_cursor
        raise _schema_error("connection_page_limit", "Linear pagination exceeded the bounded page limit")

    def inspect_binding(self, config: Mapping[str, object]) -> RemoteBinding:
        """Validate the configured workspace, team, label hierarchy, and views."""

        linear = _required_mapping(config, "linear", request_id=None)
        repository = _required_mapping(config, "repository", request_id=None)
        data = self.query(
            BINDING_QUERY,
            {
                "teamId": _required_string(linear, "team_id", request_id=None),
                "projectLabelGroupId": _required_string(repository, "project_label_group_id", request_id=None),
                "projectLabelId": _required_string(repository, "project_label_id", request_id=None),
                "projectViewId": _required_string(repository, "project_view_id", request_id=None),
                "issueViewId": _required_string(repository, "issue_view_id", request_id=None),
            },
        )
        viewer = _required_mapping(data, "viewer", request_id=None)
        organization = _required_mapping(viewer, "organization", request_id=None)
        expected_workspace = _required_string(linear, "workspace_id", request_id=None)
        if _required_string(organization, "id", request_id=None) != expected_workspace:
            raise _identity_error("workspace_mismatch", "configured workspace does not match the authenticated Linear workspace")

        team = _required_mapping(data, "team", request_id=None)
        group = _required_mapping(data, "projectLabelGroup", request_id=None)
        label = _required_mapping(data, "projectLabel", request_id=None)
        project_view = _required_mapping(data, "projectView", request_id=None)
        issue_view = _required_mapping(data, "issueView", request_id=None)
        if group.get("isGroup") is not True:
            raise _identity_error("project_label_group", "configured Project Label Group is not a group")
        if label.get("isGroup") is True:
            raise _identity_error("project_label", "configured repository Project Label cannot be a group")
        parent = _required_mapping(label, "parent", request_id=None)
        group_id = _required_string(group, "id", request_id=None)
        expected_team_id = _required_string(linear, "team_id", request_id=None)
        expected_group_id = _required_string(repository, "project_label_group_id", request_id=None)
        expected_label_id = _required_string(repository, "project_label_id", request_id=None)
        expected_project_view_id = _required_string(repository, "project_view_id", request_id=None)
        expected_issue_view_id = _required_string(repository, "issue_view_id", request_id=None)
        resource_ids = {
            "team": (_required_string(team, "id", request_id=None), expected_team_id),
            "Project Label Group": (group_id, expected_group_id),
            "repository Project Label": (_required_string(label, "id", request_id=None), expected_label_id),
            "Project Shared View": (_required_string(project_view, "id", request_id=None), expected_project_view_id),
            "Issue Shared View": (_required_string(issue_view, "id", request_id=None), expected_issue_view_id),
        }
        for resource_name, (observed_id, configured_id) in resource_ids.items():
            if observed_id != configured_id:
                raise _identity_error("binding_id_mismatch", f"configured {resource_name} did not resolve to its expected ID")
        if _required_string(team, "key", request_id=None) != _required_string(linear, "team_key", request_id=None):
            raise _identity_error("team_key_mismatch", "configured Team key does not match the remote Team")
        if _required_string(label, "name", request_id=None) != _required_string(repository, "project_label", request_id=None):
            raise _identity_error("project_label_name_mismatch", "configured repository Project Label name does not match the remote label")
        if _required_string(parent, "id", request_id=None) != group_id:
            raise _identity_error("project_label_parent", "configured repository Project Label does not belong to the configured group")
        expected_label_name = _required_string(repository, "project_label", request_id=None)
        _validate_shared_view(
            project_view,
            expected_type="project",
            filter_field="projectFilterData",
            label_scope=None,
            label_id=expected_label_id,
            label_name=expected_label_name,
            name="Project Shared View",
        )
        _validate_shared_view(
            issue_view,
            expected_type="issue",
            filter_field="filterData",
            label_scope="project",
            label_id=expected_label_id,
            label_name=expected_label_name,
            name="Issue Shared View",
        )
        return RemoteBinding(
            workspace_id=expected_workspace,
            team_id=expected_team_id,
            team_key=_required_string(team, "key", request_id=None),
            project_label_group_id=group_id,
            project_label_group_name=_required_string(group, "name", request_id=None),
            project_label_id=expected_label_id,
            project_label_name=_required_string(label, "name", request_id=None),
            project_label_parent_id=_required_string(parent, "id", request_id=None),
            project_view_id=expected_project_view_id,
            project_view_type=_required_string(project_view, "type", request_id=None),
            project_view_shared=_required_bool(project_view, "shared", request_id=None),
            issue_view_id=expected_issue_view_id,
            issue_view_type=_required_string(issue_view, "type", request_id=None),
            issue_view_shared=_required_bool(issue_view, "shared", request_id=None),
        )

    def resolve_workspace_id(self) -> str:
        """Read the authenticated workspace ID (``onboard`` auto-fills ``linear.workspace_id``).

        Reuses the exact ``viewer { organization { id } } }`` shape already
        schema-conformed inside :meth:`inspect_binding` against the real API
        (see ``validation/linear-remote-acceptance.md``); this query adds no
        new field beyond that proven shape.
        """

        data = self.query(VIEWER_ORGANIZATION_QUERY)
        viewer = _required_mapping(data, "viewer", request_id=None)
        organization = _required_mapping(viewer, "organization", request_id=None)
        return _required_string(organization, "id", request_id=None)

    def resolve_team_by_id(self, team_id: str) -> RemoteTeamSummary:
        """Read a Team's canonical key/name by ID (``onboard --team-id``).

        Not yet exercised against the real Linear API; the ``id`` argument
        type follows ``BINDING_QUERY``'s already schema-conformed
        ``String!`` convention for this class of root field, but that
        inference has not itself been remote-verified.
        """

        data = self.query(TEAM_BY_ID_QUERY, {"id": team_id})
        team = _required_mapping(data, "team", request_id=None)
        return RemoteTeamSummary(
            id=_required_string(team, "id", request_id=None),
            key=_required_string(team, "key", request_id=None),
            name=_required_string(team, "name", request_id=None),
        )

    def find_team_by_key(self, key: str) -> tuple[RemoteTeamSummary, ...]:
        """List every Team with an exact key match (``onboard --team-key``).

        Not yet exercised against the real Linear API; unlike an ``id``
        argument on a single-entity root field, ``key`` here flows through a
        connection filter comparator, matching the already-used
        ``String!``-typed ``name``/``key`` filter fields in the by-name
        queries above.
        """

        nodes = self.connection(TEAMS_BY_KEY_QUERY, root_key="teams", variables={"key": key})
        return tuple(
            RemoteTeamSummary(
                id=_required_string(node, "id", request_id=None),
                key=_required_string(node, "key", request_id=None),
                name=_required_string(node, "name", request_id=None),
            )
            for node in nodes
        )

    def find_workflow_states_by_team(self, team_id: str) -> tuple[RemoteWorkflowState, ...]:
        """List every workflow state for a Team (``onboard``'s lifecycle sync, on by default).

        Unlike :meth:`find_workflow_states_by_name`, this is not scoped by
        name: the caller filters by ``type`` (``completed``/``unstarted``)
        itself and breaks ties by ``position``.
        """

        nodes = self.connection(WORKFLOW_STATES_BY_TEAM_QUERY, root_key="workflowStates", variables={"teamId": team_id})
        return tuple(_remote_workflow_state(node) for node in nodes)

    def find_git_automation_states(self, team_id: str) -> tuple[RemoteGitAutomationState, ...]:
        """List the Team's PR-automation mappings (``onboard``'s automation sync)."""

        data = self.query(GIT_AUTOMATION_STATES_BY_TEAM_QUERY, {"teamId": team_id})
        team = data.get("team")
        if not isinstance(team, Mapping):
            return ()
        states = team.get("gitAutomationStates")
        nodes = states.get("nodes") if isinstance(states, Mapping) else None
        if not isinstance(nodes, list):
            return ()
        return tuple(
            RemoteGitAutomationState(
                id=_required_string(node, "id", request_id=None),
                event=_required_string(node, "event", request_id=None),
                state_id=_optional_id(node, "state"),
                state_name=_optional_nested_string(node, "state", "name"),
                target_branch_id=_optional_id(node, "targetBranch"),
            )
            for node in nodes
            if isinstance(node, Mapping)
        )

    def has_github_integration(self) -> bool:
        """Whether the workspace's GitHub integration is connected (read-only)."""

        nodes = self.connection(GITHUB_INTEGRATION_QUERY, root_key="integrations", variables={})
        return any(isinstance(node, Mapping) and node.get("service") == "github" for node in nodes)


    def find_project_labels_by_name(self, name: str) -> tuple[RemoteProjectLabel, ...]:
        """List every project label with an exact name match (`onboard`)."""

        nodes = self.connection(PROJECT_LABELS_BY_NAME_QUERY, root_key="projectLabels", variables={"name": name})
        return tuple(
            RemoteProjectLabel(
                id=_required_string(node, "id", request_id=None),
                name=_required_string(node, "name", request_id=None),
                is_group=_required_bool(node, "isGroup", request_id=None),
                updated_at=_required_string(node, "updatedAt", request_id=None),
                parent_id=_optional_id(node, "parent"),
            )
            for node in nodes
        )

    def find_shared_views_by_name(self, name: str) -> tuple[RemoteSharedView, ...]:
        """List every Shared View with an exact name match.

        Used by ``onboard`` to resolve the two
        conventional Shared View names ("<repository slug> / Features",
        "<repository slug> / Work") without guessing an ID. Not yet
        exercised against a live workspace; see ``SHARED_VIEWS_BY_NAME_QUERY``.
        """

        nodes = self.connection(SHARED_VIEWS_BY_NAME_QUERY, root_key="customViews", variables={"name": name})
        return tuple(
            RemoteSharedView(
                id=_required_string(node, "id", request_id=None),
                name=_required_string(node, "name", request_id=None),
                type=_required_string(node, "type", request_id=None),
                shared=_required_bool(node, "shared", request_id=None),
                updated_at=_required_string(node, "updatedAt", request_id=None),
            )
            for node in nodes
        )

    def find_issues_by_numbers(self, team_id: str, numbers: Sequence[int]) -> tuple[RemoteWorkItem, ...]:
        """Read every Team Issue whose number is in ``numbers``, in one batched query.

        The one remote read Stage 5 adds. An empty request never reaches the
        network at all, which is what keeps a repository with no bug or chore
        branch exactly as cheap as it was before.
        """

        if not numbers:
            return ()
        nodes = self.connection(
            WORK_ITEM_ISSUES_QUERY,
            root_key="issues",
            variables={"teamId": team_id, "numbers": [float(number) for number in sorted(set(numbers))]},
        )
        return tuple(
            RemoteWorkItem(
                id=_required_string(node, "id", request_id=None),
                identifier=_required_string(node, "identifier", request_id=None),
                title=_required_string(node, "title", request_id=None),
                updated_at=_required_string(node, "updatedAt", request_id=None),
                state_id=_optional_id(node, "state"),
                state_name=_optional_nested_string(node, "state", "name"),
                url=_optional_string(node, "url"),
            )
            for node in nodes
        )

    def discover_projects(self, project_label_id: str) -> tuple[RemoteProject, ...]:
        """Discover every project under a repository label and its local graph."""

        project_nodes = self.connection(
            FEATURE_PROJECTS_QUERY,
            root_key="projects",
            variables={"projectLabelId": project_label_id},
        )
        projects: list[RemoteProject] = []
        for node in project_nodes:
            project_id = _required_string(node, "id", request_id=None)
            issue_nodes = self.connection(
                PROJECT_ISSUES_QUERY,
                root_key="issues",
                variables={"projectId": project_id},
            )
            projects.append(
                RemoteProject(
                    id=project_id,
                    name=_required_string(node, "name", request_id=None),
                    description=_optional_string(node, "description"),
                    updated_at=_required_string(node, "updatedAt", request_id=None),
                    team_ids=_connection_ids(node, "teams"),
                    label_ids=_connection_ids(node, "labels"),
                    issues=tuple(_remote_issue(item) for item in issue_nodes),
                    lead_id=_optional_id(node, "lead"),
                    member_ids=_optional_connection_ids(node, "members"),
                    content=_optional_string(node, "content"),
                )
            )
        return tuple(projects)

    def _execute_once(self, payload: bytes, request_id: str) -> dict[str, object]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"spec-kit-linear/{__version__}",
            "X-SpecKit-Linear-Request-Id": request_id,
            **self.credentials.headers(),
        }
        request = Request(self.endpoint, data=payload, headers=headers, method="POST")
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                status_value = getattr(response, "status", None)
                status = int(status_value if status_value is not None else response.getcode())
                response_headers = _header_mapping(getattr(response, "headers", {}))
                body = _read_bounded(response)
        except HTTPError as error:
            status = int(error.code)
            response_headers = _header_mapping(error.headers or {})
            body = _read_bounded(error)
        except (URLError, TimeoutError, socket.timeout, RemoteDisconnected, OSError) as error:
            raise AppError(
                "Linear read request could not reach the service",
                code=8,
                category="transport",
                diagnostics=[Diagnostic("linear_transport", "request transport failed", redact_text(self.endpoint))],
                retryable=True,
            ) from error
        return self._decode_response(status, response_headers, body, request_id)

    def _decode_response(
        self,
        status: int,
        headers: Mapping[str, str],
        body: bytes,
        request_id: str,
    ) -> dict[str, object]:
        if status in {401, 403}:
            raise _authorization_error(status, request_id, source=self.credentials.source)
        if 300 <= status < 400:
            # See _RefuseRedirects: a 3xx reaches this point only because the
            # redirect was refused. Permanent and never retried -- following
            # it would hand the credential to a destination the endpoint
            # validator never approved.
            raise AppError(
                "Linear endpoint answered with a redirect, which is never followed",
                code=9,
                category="transport",
                diagnostics=[
                    Diagnostic(
                        "linear_redirect",
                        f"HTTP {status}: the configured endpoint redirected elsewhere; the credential is never sent to a destination the endpoint validator did not approve",
                        redact_text(self.endpoint),
                    ),
                    Diagnostic("linear_request", request_id, severity="info"),
                ],
            )
        if status == 429:
            raise _rate_limit_error(headers, request_id, self.endpoint)
        if status >= 500:
            raise AppError(
                "Linear service did not complete this read request",
                code=8,
                category="service",
                diagnostics=[Diagnostic("linear_service", f"HTTP {status}", redact_text(self.endpoint)), Diagnostic("linear_request", request_id, severity="info")],
                retryable=True,
            )
        try:
            document = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise _schema_error("linear_invalid_json", "Linear response was not valid JSON", request_id=request_id) from error
        if not isinstance(document, dict):
            raise _schema_error("linear_response_shape", "Linear response must be a JSON object", request_id=request_id)
        errors = document.get("errors")
        if _has_rate_limited_error(errors):
            raise _rate_limit_error(headers, request_id, self.endpoint)
        if not 200 <= status < 300:
            raise AppError(
                "Linear rejected this request",
                code=9,
                category="graphql",
                diagnostics=[Diagnostic("linear_http", f"HTTP {status}", redact_text(self.endpoint)), Diagnostic("linear_request", request_id, severity="info")],
            )
        if errors is not None:
            raise _graphql_error(errors, request_id)
        data = document.get("data")
        if not isinstance(data, dict):
            raise _schema_error("linear_data", "Linear response data must be an object", request_id=request_id)
        return data

    def _retry_delay(self, error: AppError, attempt: int) -> float:
        header_delay = 0.0
        for diagnostic in error.diagnostics:
            if diagnostic.code == "linear_retry_after" and diagnostic.message.startswith("seconds="):
                try:
                    header_delay = max(header_delay, float(diagnostic.message.split("=", 1)[1]))
                except ValueError:
                    continue
        exponential = min(5.0, 0.25 * (2 ** (attempt - 1)))
        return min(10.0, max(header_delay, exponential) + self._jitter(0.0, 0.1))


def _validate_endpoint(value: str) -> str:
    """Delegate to the single endpoint validator (doc "Override de endpoint").

    Kept as a thin alias so the client still refuses an endpoint handed to it
    programmatically, while the rules themselves live in exactly one module.
    A rejection is exit code 3 (invalid configuration), the same code the CLI
    returns when the environment override itself is invalid.
    """

    return validate_endpoint(value, origin="the Linear GraphQL endpoint")


def _read_bounded(response: Any) -> bytes:
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if not isinstance(body, bytes):
        raise _schema_error("linear_response_bytes", "Linear response body must be bytes")
    if len(body) > MAX_RESPONSE_BYTES:
        raise _schema_error("linear_response_limit", "Linear response exceeded the bounded body limit")
    return body


def _header_mapping(headers: Any) -> dict[str, str]:
    if hasattr(headers, "items"):
        return {str(key).lower(): str(value) for key, value in headers.items()}
    return {}


def _has_rate_limited_error(errors: object) -> bool:
    if not isinstance(errors, list):
        return False
    for error in errors:
        if not isinstance(error, dict):
            continue
        extensions = error.get("extensions")
        if isinstance(extensions, dict) and extensions.get("code") == "RATELIMITED":
            return True
    return False


def _rate_limit_diagnostics(headers: Mapping[str, str]) -> list[Diagnostic]:
    delay = _rate_limit_delay(headers)
    return [Diagnostic("linear_retry_after", f"seconds={delay:.3f}", severity="info")]


def _rate_limit_error(headers: Mapping[str, str], request_id: str, endpoint: str) -> AppError:
    return AppError(
        "Linear rate limit delayed this read request",
        code=8,
        category="rate_limit",
        diagnostics=[
            Diagnostic("linear_rate_limit", "Linear requested a bounded retry", redact_text(endpoint)),
            Diagnostic("linear_request", request_id, severity="info"),
            *_rate_limit_diagnostics(headers),
        ],
        retryable=True,
    )


def _rate_limit_delay(headers: Mapping[str, str]) -> float:
    retry_after = headers.get("retry-after")
    if retry_after is not None:
        try:
            return min(10.0, max(0.0, float(retry_after)))
        except ValueError:
            pass
    reset = headers.get("x-ratelimit-reset")
    if reset is not None:
        try:
            reset_value = float(reset)
            if reset_value > 10_000_000_000:
                reset_value /= 1000.0
            return min(10.0, max(0.0, reset_value - time.time()))
        except ValueError:
            pass
    return 0.0


def _graphql_error(errors: object, request_id: str) -> AppError:
    if not isinstance(errors, list) or not errors:
        return _schema_error("linear_errors", "Linear response errors must be a non-empty list", request_id=request_id)
    codes: list[str] = []
    messages: list[str] = []
    for item in errors:
        if not isinstance(item, dict):
            return _schema_error("linear_errors", "Linear response errors must contain objects", request_id=request_id)
        extensions = item.get("extensions")
        code = extensions.get("code") if isinstance(extensions, dict) else None
        if isinstance(code, str) and code.isupper() and len(code) <= 64:
            codes.append(code)
        presentable = extensions.get("userPresentableMessage") if isinstance(extensions, dict) else None
        # For INVALID_INPUT, `message` is typically the generic "Argument
        # Validation Error"; the actionable text (e.g. "name must be shorter
        # than or equal to 80 characters") lives in `userPresentableMessage`.
        # Prefer it when present, since a bare code once cost a debugging
        # session to recover the remediation. Redacted either way, because a
        # server message can echo credentials or user content.
        message = presentable if isinstance(presentable, str) and presentable.strip() else item.get("message")
        if isinstance(message, str) and message.strip():
            messages.append(redact_text(message.strip()[:200]))
    diagnostic = ",".join(sorted(set(codes))) if codes else "unspecified"
    diagnostics = [Diagnostic("linear_graphql", f"codes={diagnostic}"), Diagnostic("linear_request", request_id, severity="info")]
    for message in messages[:3]:
        diagnostics.append(Diagnostic("linear_graphql_message", message, severity="warning"))
    return AppError(
        "Linear returned GraphQL errors for this request",
        code=9,
        category="graphql",
        diagnostics=diagnostics,
    )


def _authorization_error(status: int, request_id: str, *, source: str | None = None) -> AppError:
    category = "authentication" if status == 401 else "authorization"
    diagnostics = [Diagnostic("linear_auth", f"HTTP {status}"), Diagnostic("linear_request", request_id, severity="info")]
    if source is not None:
        # The path (or "the process environment") that defined the rejected
        # credential — never its value. Renewal starts there.
        diagnostics.append(Diagnostic("linear_credentials_source", f"the credential was defined in {source}; renew it there", severity="warning"))
    return AppError(
        f"Linear {category} failed for this request",
        code=5,
        category=category,
        diagnostics=diagnostics,
    )


def _schema_error(code: str, message: str, *, request_id: str | None = None) -> AppError:
    diagnostics = [Diagnostic(code, message)]
    if request_id:
        diagnostics.append(Diagnostic("linear_request", request_id, severity="info"))
    return AppError(message, code=9, category="graphql", diagnostics=diagnostics)


def _identity_error(code: str, message: str) -> AppError:
    return AppError(message, code=6, category="remote_identity", diagnostics=[Diagnostic(code, message)])


def _validate_shared_view(
    view: Mapping[str, object],
    *,
    expected_type: str,
    filter_field: str,
    label_scope: str | None,
    label_id: str,
    label_name: str,
    name: str,
) -> None:
    observed_type = _required_string(view, "type", request_id=None).lower()
    if observed_type != expected_type:
        raise _identity_error("shared_view_type", f"{name} must have type '{expected_type}'")
    if _required_bool(view, "shared", request_id=None) is not True:
        raise _identity_error("shared_view_scope", f"{name} must be shared in the configured workspace")
    actual_filter = _normalize_json_structure(view.get(filter_field), filter_field)
    if not _filter_targets_label(actual_filter, label_scope=label_scope, label_id=label_id, label_name=label_name):
        raise _identity_error("shared_view_filter", f"{name} does not contain the required repository label filter")


def _filter_targets_label(filter_tree: object, *, label_scope: str | None, label_id: str, label_name: str) -> bool:
    """True when the view filter targets the repository Project Label.

    Linear's saved-view UI serializes label filters by name and wraps them in
    ``and``/``or`` lists, while the API's canonical ProjectFilter uses
    ``labels.some.id.eq``.  Views are recreatable navigation, never identity,
    so both serializations are accepted anywhere inside the filter tree.  For
    Issue views (``label_scope='project'``) the label subtree must live under a
    ``project`` key so the view follows the label, not one pinned Project.
    """

    scoped = _subtrees_under_key(filter_tree, label_scope) if label_scope else [filter_tree]
    label_forms: tuple[dict[str, object], ...] = (
        {"id": {"eq": label_id}},
        {"id": {"in": [label_id]}},
        {"name": {"eq": label_name}},
    )
    for scope_tree in scoped:
        for labels_tree in _subtrees_under_key(scope_tree, "labels"):
            if any(_structure_anywhere(labels_tree, form) for form in label_forms):
                return True
    return False


def _subtrees_under_key(tree: object, key: str) -> list[object]:
    found: list[object] = []
    if isinstance(tree, dict):
        for tree_key, value in tree.items():
            if tree_key == key:
                found.append(value)
            found.extend(_subtrees_under_key(value, key))
    elif isinstance(tree, list):
        for item in tree:
            found.extend(_subtrees_under_key(item, key))
    return found


def _structure_anywhere(tree: object, expected: object) -> bool:
    if _contains_structure(tree, expected):
        return True
    if isinstance(tree, dict):
        return any(_structure_anywhere(value, expected) for value in tree.values())
    if isinstance(tree, list):
        return any(_structure_anywhere(item, expected) for item in tree)
    return False


def _normalize_json_structure(value: object, field: str, *, serialized: bool = True) -> object:
    """Normalize JSON scalar serialization so filter comparison is structural."""

    if serialized and isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise _identity_error("shared_view_filter", f"Linear {field} is not valid JSON") from error
    if isinstance(value, dict):
        return {str(key): _normalize_json_structure(nested, field, serialized=False) for key, nested in value.items()}
    if isinstance(value, list):
        return [_normalize_json_structure(item, field, serialized=False) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise _identity_error("shared_view_filter", f"Linear {field} has an unsupported JSON shape")


def _contains_structure(actual: object, expected: object) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains_structure(actual[key], expected_value)
            for key, expected_value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and all(any(_contains_structure(candidate, item) for candidate in actual) for item in expected)
    return actual == expected


def _required_mapping(parent: Mapping[str, object], key: str, *, request_id: str | None) -> dict[str, object]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise _schema_error("linear_nullability", f"Linear response '{key}' must be an object", request_id=request_id)
    return value


def _required_string(parent: Mapping[str, object], key: str, *, request_id: str | None) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value:
        raise _schema_error("linear_nullability", f"Linear response '{key}' must be a non-empty string", request_id=request_id)
    return value


def _required_bool(parent: Mapping[str, object], key: str, *, request_id: str | None) -> bool:
    value = parent.get(key)
    if not isinstance(value, bool):
        raise _schema_error("linear_nullability", f"Linear response '{key}' must be boolean", request_id=request_id)
    return value


def _optional_string(parent: Mapping[str, object], key: str) -> str:
    value = parent.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise _schema_error("linear_nullability", f"Linear response '{key}' must be string or null")
    return value


def _optional_id(parent: Mapping[str, object], key: str) -> str | None:
    value = parent.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _schema_error("linear_nullability", f"Linear response '{key}' must be an object or null")
    return _required_string(value, "id", request_id=None)


def _optional_nested_string(parent: Mapping[str, object], key: str, nested_key: str) -> str | None:
    """Read an optional string off a nullable nested object (e.g. ``assignee.displayName``).

    Mirrors ``_optional_id``'s null-object handling, but for a sibling
    string field instead of ``id``: a ``None``/absent object yields ``None``,
    and a present object requires the nested field to be a non-null string.
    """

    value = parent.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _schema_error("linear_nullability", f"Linear response '{key}' must be an object or null")
    return _required_string(value, nested_key, request_id=None)


def _connection_ids(parent: Mapping[str, object], key: str) -> tuple[str, ...]:
    connection = _required_mapping(parent, key, request_id=None)
    nodes = connection.get("nodes")
    if not isinstance(nodes, list) or not all(isinstance(node, dict) for node in nodes):
        raise _schema_error("linear_nullability", f"Linear response '{key}.nodes' must be object nodes")
    return tuple(_required_string(node, "id", request_id=None) for node in nodes)


def _remote_workflow_state(node: Mapping[str, object]) -> RemoteWorkflowState:
    position = node.get("position")
    if not isinstance(position, (int, float)) or isinstance(position, bool):
        raise _schema_error("linear_nullability", "Linear response 'position' must be numeric")
    return RemoteWorkflowState(
        id=_required_string(node, "id", request_id=None),
        name=_required_string(node, "name", request_id=None),
        type=_required_string(node, "type", request_id=None),
        updated_at=_required_string(node, "updatedAt", request_id=None),
        position=float(position),
    )


def _remote_issue(node: Mapping[str, object]) -> RemoteIssue:
    project = _required_mapping(node, "project", request_id=None)
    return RemoteIssue(
        id=_required_string(node, "id", request_id=None),
        identifier=_required_string(node, "identifier", request_id=None),
        title=_required_string(node, "title", request_id=None),
        description=_optional_string(node, "description"),
        updated_at=_required_string(node, "updatedAt", request_id=None),
        project_id=_required_string(project, "id", request_id=None),
        parent_id=_optional_id(node, "parent"),
        assignee_id=_optional_id(node, "assignee"),
        label_ids=_connection_ids(node, "labels"),
        state_id=_optional_id(node, "state"),
        assignee_name=_optional_nested_string(node, "assignee", "displayName"),
        state_name=_optional_nested_string(node, "state", "name"),
        url=_optional_string(node, "url"),
    )


def _optional_connection_ids(parent: Mapping[str, object], key: str) -> tuple[str, ...]:
    if key not in parent or parent.get(key) is None:
        return ()
    return _connection_ids(parent, key)
