#!/usr/bin/env python3
"""Resolve a Linear Issue and validate the branch before Git setup."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from _common import die, run_git


KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-[0-9]+$")
RESERVED_RE = re.compile(r"^[0-9]{3}(?:-T[0-9]{3})?-[^/]+$")


@dataclass(frozen=True)
class WorkItemContext:
    issue_key: str
    title: str
    description: str
    branch_name: str
    url: str = ""
    configured: bool = False


@dataclass(frozen=True)
class StartPlan:
    context: WorkItemContext
    existing: bool = False
    remote_ref: str | None = None


@dataclass(frozen=True)
class PullRequestObservation:
    head_branch: str
    body: str
    state: str
    same_repo: bool


ISSUE_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]*)-([0-9]+)(?![A-Za-z0-9])")
TRACKER_SECTION_RE = re.compile(r"(?ms)^##[ \t]+Work item[ \t]*\r?\n(?P<section>.*?)(?=^#{1,6}[ \t]+|\Z)")
TRACKER_LINE_RE = re.compile(r"(?m)^[ ]{0,3}-[ \t]+Tracker:[ \t]*(?P<value>.*?)[ \t]*$")
TRACKER_VALUE_RE = re.compile(r"^Fixes[ \t]+(?P<key>[A-Za-z][A-Za-z0-9]*-[0-9]+)[ \t]*$")


def _issue_key(value: str) -> str:
    key = value.strip()
    if not KEY_RE.fullmatch(key):
        die("Issue key must match TEAM-number")
    return key


def _resolver_script(repo_root: Path) -> Path | None:
    path = repo_root / ".specify" / "extensions" / "linear" / "scripts" / "python" / "resolve_work_item.py"
    return path if path.is_file() else None


def _main_root(repo_root: Path) -> Path | None:
    result = run_git("rev-parse", "--git-common-dir", cwd=repo_root)
    if result.returncode != 0:
        return None
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = repo_root / common
    return common.resolve().parent if common.name == ".git" else None


def _selected_config(repo_root: Path) -> bool:
    main_root = _main_root(repo_root)
    process_value = os.environ.get("SPECKIT_LINEAR_CONFIG")
    if process_value is not None:
        if process_value.strip():
            return True
        config = repo_root / "speckit-linear.yml"
        return os.path.lexists(config) or bool(main_root and os.path.lexists(main_root / "speckit-linear.yml"))
    repo_env = repo_root / ".speckit-linear.env"
    if not repo_env.exists() and main_root is not None:
        repo_env = main_root / ".speckit-linear.env"
    env_paths = [repo_env, Path.home() / ".config/speckit-linear/env"]
    for path in env_paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError):
            continue
        selected = None
        for raw in lines:
            key, separator, value = raw.strip().partition("=")
            key = key.strip()
            if key != "SPECKIT_LINEAR_CONFIG":
                continue
            if not separator:
                die("selected Linear configuration is malformed")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            selected = value
        if selected is not None:
            if selected:
                return True
            break
    config = repo_root / "speckit-linear.yml"
    if os.path.lexists(config):
        return True
    return bool(main_root and os.path.lexists(main_root / "speckit-linear.yml"))


def _configured(repo_root: Path) -> bool:
    selected = _selected_config(repo_root)
    extension = repo_root / ".specify" / "extensions" / "linear"
    source = extension / "src"
    if not source.is_dir():
        return selected
    try:
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))
        from spec_kit_linear.config import resolve_config_path
        from spec_kit_linear.env_files import load_dotenv_files

        environment = dict(os.environ)
        load_dotenv_files(repo_root, environment)
        selected_path = environment.get("SPECKIT_LINEAR_CONFIG")
        return bool(selected_path) or os.path.lexists(resolve_config_path(repo_root, selected_path))
    except Exception:
        die("cannot inspect installed Linear configuration")


def _diagnostic(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        details = payload.get("diagnostics")
        if isinstance(details, list):
            messages = [item.get("message") for item in details if isinstance(item, dict)]
            if any(isinstance(message, str) and message.strip() for message in messages):
                return "; ".join(message.strip() for message in messages if isinstance(message, str) and message.strip())
    return fallback


def _native(repo_root: Path, script: Path, issue_key: str) -> WorkItemContext | None:
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(repo_root)],
        cwd=repo_root,
        input=json.dumps({"issue_key": issue_key}),
        text=True,
        capture_output=True,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        die("configured Linear work-item resolver returned invalid JSON")
    if result.returncode != 0:
        die(f"configured Linear work-item resolution failed: {_diagnostic(payload, 'resolver failed')}")
    status = payload.get("status") if isinstance(payload, dict) else None
    if status == "absent":
        return None
    if status != "resolved" or not isinstance(payload, dict):
        die(f"configured Linear work-item resolution failed: {_diagnostic(payload, 'resolver returned no Issue')}")
    resolution = payload.get("resolution")
    if not isinstance(resolution, dict):
        die("configured Linear work-item resolution returned no Issue context")
    branch = resolution.get("branch_name")
    title = resolution.get("title")
    description = resolution.get("description")
    identifier = resolution.get("identifier")
    url = resolution.get("url", "")
    if not all(isinstance(value, str) and value.strip() for value in (branch, title, identifier)):
        die("configured Linear work-item resolution returned incomplete Issue context")
    if not isinstance(description, str) or not isinstance(url, str):
        die("configured Linear work-item resolution returned malformed Issue context")
    return WorkItemContext(identifier, title, description, branch, url, True)


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")


def _validate_branch(repo_root: Path, branch: str) -> None:
    if not branch or branch == "HEAD" or branch.startswith("-"):
        die("Issue branch name is invalid: HEAD and leading-dash names are not allowed")
    if RESERVED_RE.fullmatch(branch):
        die(f"Issue branch name collides with a reserved feature/task name: {branch}")
    checked = run_git("check-ref-format", "--branch", branch, cwd=repo_root)
    if checked.returncode != 0 or checked.stdout.strip() != branch:
        die(f"Issue branch name is not a valid Git branch: {branch}")
    ref_checked = run_git("check-ref-format", f"refs/heads/{branch}", cwd=repo_root)
    if ref_checked.returncode != 0:
        die(f"Issue branch name is not a valid Git ref: {branch}")


def _same_issue(left: str, right: str) -> bool:
    if not KEY_RE.fullmatch(left.strip()) or not KEY_RE.fullmatch(right.strip()):
        return False
    left_team, left_number = left.strip().split("-", 1)
    right_team, right_number = right.strip().split("-", 1)
    return left_team.casefold() == right_team.casefold() and int(left_number) == int(right_number)


def _strict_keys(branch: str) -> list[str]:
    if re.fullmatch(r"(?:[^/]+/)?[A-Za-z][A-Za-z0-9]*-[0-9]+(?:-[^/]*)?", branch) is None:
        return []
    return list(dict.fromkeys(match.group(0) for match in ISSUE_TOKEN_RE.finditer(branch.rsplit("/", 1)[-1])))


def _fence_start(line: str) -> tuple[str, int] | None:
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3 or not stripped:
        return None
    marker = stripped[0]
    if marker not in {"`", "~"}:
        return None
    length = len(stripped) - len(stripped.lstrip(marker))
    if length < 3 or (marker == "`" and marker in stripped[length:]):
        return None
    return marker, length


def _fence_end(line: str, marker: str, opening_length: int) -> bool:
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return False
    candidate = stripped.rstrip(" \t")
    return len(candidate) >= opening_length and candidate == marker * len(candidate)


def _matchable_lines(lines: list[str]) -> list[bool]:
    matchable: list[bool] = []
    fence: tuple[str, int] | None = None
    for line in lines:
        if fence is None:
            fence = _fence_start(line)
            matchable.append(fence is None)
        else:
            matchable.append(False)
            if _fence_end(line, *fence):
                fence = None
    return matchable


def _local_tracker_keys(body: str) -> tuple[list[str], bool]:
    lines = body.splitlines()
    matchable = _matchable_lines(lines)
    visible = "\n".join(line if allowed else "" for line, allowed in zip(lines, matchable))
    values = [
        match.group("value")
        for section in TRACKER_SECTION_RE.finditer(visible)
        for match in TRACKER_LINE_RE.finditer(section.group("section"))
    ]
    keys: list[str] = []
    malformed = False
    for value in values:
        match = TRACKER_VALUE_RE.fullmatch(value)
        if match is None:
            malformed = True
            continue
        key = match.group("key")
        if key not in keys:
            keys.append(key)
    return keys, malformed


def branch_refs(repo_root: Path) -> dict[str, tuple[bool, str | None]]:
    result = run_git("for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes", cwd=repo_root)
    if result.returncode != 0:
        die(result.stderr.strip() or "cannot observe local and remote branches")
    refs: dict[str, tuple[bool, str | None]] = {}
    for ref in result.stdout.splitlines():
        if ref.startswith("refs/heads/"):
            refs[ref.removeprefix("refs/heads/")] = (True, refs.get(ref.removeprefix("refs/heads/"), (False, None))[1])
        elif ref.startswith("refs/remotes/"):
            value = ref.removeprefix("refs/remotes/")
            remote, separator, branch = value.partition("/")
            if separator and branch and branch != "HEAD":
                remote_ref = f"{remote}/{branch}"
                existing = refs.get(branch)
                if existing is not None and existing[1] is not None and existing[1] != remote_ref:
                    die(f"multiple remote heads share the existing branch name: {branch}")
                refs[branch] = (existing[0] if existing else False, remote_ref)
    return refs


def _hosted_remote(remote: str) -> bool:
    return remote.startswith("git@") or ("://" in remote and not remote.startswith("file://"))


def pull_requests(repo_root: Path) -> tuple[PullRequestObservation, ...]:
    remote = run_git("remote", "get-url", "origin", cwd=repo_root)
    if remote.returncode != 0:
        return ()
    remote_url = remote.stdout.strip()
    if shutil.which("gh") is None:
        if _hosted_remote(remote_url):
            die("GitHub pull-request observation is unavailable; install gh before starting work")
        return ()
    try:
        result = subprocess.run(
            ["gh", "api", "repos/{owner}/{repo}/pulls", "--paginate", "--slurp", "--method", "GET",
             "-H", "X-GitHub-Api-Version: 2022-11-28", "-f", "state=all", "-f", "per_page=100"],
            cwd=repo_root, text=True, capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        if not _hosted_remote(remote_url):
            return ()
        die("GitHub pull-request observation failed; existing work cannot be verified")
    if result.returncode != 0:
        if not _hosted_remote(remote_url):
            return ()
        die("GitHub pull-request observation failed; existing work cannot be verified")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        die("GitHub pull-request observation returned invalid JSON")
    pages: list[Any]
    if not isinstance(payload, list):
        die("GitHub pull-request observation returned malformed JSON")
    if payload and all(isinstance(page, list) for page in payload):
        pages = [item for page in payload for item in page]
    else:
        pages = payload
    observations: list[PullRequestObservation] = []
    for item in pages:
        if not isinstance(item, dict) or not isinstance(item.get("head"), dict) or not isinstance(item.get("base"), dict):
            die("GitHub pull-request observation returned malformed data")
        head, base = item["head"], item["base"]
        branch = head.get("ref")
        state = item.get("state")
        if not isinstance(branch, str) or not branch or not isinstance(state, str):
            die("GitHub pull-request observation returned malformed data")
        head_repo = head.get("repo") if isinstance(head.get("repo"), dict) else {}
        base_repo = base.get("repo") if isinstance(base.get("repo"), dict) else {}
        same_repo = bool(head_repo.get("full_name") and head_repo.get("full_name") == base_repo.get("full_name"))
        body = item.get("body")
        if body is None:
            body = ""
        if not isinstance(body, str):
            die("GitHub pull-request observation returned malformed body")
        observations.append(PullRequestObservation(branch, body, state.upper(), same_repo))
    return tuple(observations)


def _bridge_observations(
    repo_root: Path,
    script: Path,
    branches: list[str],
    prs: tuple[PullRequestObservation, ...],
) -> list[dict[str, Any]]:
    request: dict[str, object] = {"branch_names": branches}
    request["pull_requests"] = [{"head_branch": item.head_branch, "body": item.body} for item in prs]
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(repo_root)], cwd=repo_root,
        input=json.dumps(request), text=True, capture_output=True,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        die("configured Linear work-item resolver returned invalid JSON")
    if result.returncode != 0 or not isinstance(payload, dict) or payload.get("status") == "error":
        die(f"configured Linear work-item observation failed: {_diagnostic(payload, 'resolver failed')}")
    observations = payload.get("observations")
    if not isinstance(observations, list) or len(observations) != len(branches) + len(prs):
        die("configured Linear work-item resolver returned incomplete observations")
    if not all(isinstance(item, dict) for item in observations):
        die("configured Linear work-item resolver returned malformed observations")
    for item in observations:
        affected = item.get("affected_issue_keys")
        if not isinstance(affected, list) or any(
            not isinstance(key, str) or not KEY_RE.fullmatch(key.strip()) for key in affected
        ):
            die("configured Linear work-item resolver returned missing or malformed affected Issue keys")
    return observations


def _adopt(
    issue_key: str,
    refs: dict[str, tuple[bool, str | None]],
    prs: tuple[PullRequestObservation, ...],
    observations: list[dict[str, Any]] | None,
    observed_branches: list[str] | None = None,
) -> str | None:
    branch_candidates: set[str] = set()
    open_candidates: set[str] = set()
    blockers: list[str] = []
    ambiguous_branches: set[str] = set()
    originally_ambiguous: set[str] = set()
    local_tracker_keys: dict[str, set[str]] = {}
    local_tracker_malformed: set[str] = set()
    local_tracker_missing: set[str] = set()
    branches = observed_branches if observations is not None and observed_branches is not None else sorted(refs)
    branch_count = len(branches)
    for index, branch in enumerate(branches):
        evidence = observations[index] if observations is not None else None
        if observations is None:
            strict = _strict_keys(branch)
            if any(_same_issue(key, issue_key) for key in strict) and len(strict) == 1:
                branch_candidates.add(branch)
            elif any(_same_issue(key, issue_key) for key in strict):
                ambiguous_branches.add(branch)
                originally_ambiguous.add(branch)
            continue
        status = evidence.get("status") if evidence else None
        identity = evidence["affected_issue_keys"]
        resolution = evidence.get("resolution") if evidence else None
        identifier = resolution.get("identifier") if isinstance(resolution, dict) else None
        if status == "resolved" and isinstance(identifier, str) and _same_issue(identifier, issue_key):
            branch_candidates.add(branch)
        elif status in {"unresolved", "conflict"} and any(_same_issue(key, issue_key) for key in identity):
            blockers.append(f"existing branch identity is {status}: {branch}")

    for index, item in enumerate(prs):
        evidence = observations[branch_count + index] if observations is not None else None
        status = None
        if observations is None:
            if RESERVED_RE.fullmatch(item.head_branch):
                continue
            strict = _strict_keys(item.head_branch)
            tracker, malformed = _local_tracker_keys(item.body)
            local_tracker_keys.setdefault(item.head_branch, set()).update(tracker)
            if not tracker:
                local_tracker_missing.add(item.head_branch)
            if malformed:
                local_tracker_malformed.add(item.head_branch)
            identity = list(dict.fromkeys(strict[:1] + tracker))
            explicit_target = any(_same_issue(key, issue_key) for key in identity)
            conflict = malformed or len(tracker) > 1 or (strict and tracker and tracker != [strict[0]])
            if conflict and explicit_target:
                blockers.append(f"pull-request identity is conflicting: {item.head_branch}")
                continue
            tracker_target = any(_same_issue(key, issue_key) for key in tracker)
            target = tracker_target or (len(strict) == 1 and explicit_target)
        else:
            identity = evidence["affected_issue_keys"]
            explicit_target = any(_same_issue(key, issue_key) for key in identity)
            status = evidence.get("status") if evidence else None
            resolution = evidence.get("resolution") if evidence else None
            identifier = resolution.get("identifier") if isinstance(resolution, dict) else None
            target = status == "resolved" and isinstance(identifier, str) and _same_issue(identifier, issue_key)
        if status in {"unresolved", "conflict"} and explicit_target:
            blockers.append(f"pull-request identity is {status}: {item.head_branch}")
            continue
        if not target:
            continue
        if not item.same_repo:
            blockers.append(f"cannot adopt pull request from a fork: {item.head_branch}")
        elif item.state == "OPEN":
            if observations is None:
                ambiguous_branches.discard(item.head_branch)
            open_candidates.add(item.head_branch)

    if observations is None:
        for branch in sorted(ambiguous_branches):
            blockers.append(f"conflicting existing branch identity: {branch}")
        for branch in sorted(originally_ambiguous & local_tracker_missing):
            blockers.append(f"pull-request identity is unresolved: {branch}")
        for branch, keys in local_tracker_keys.items():
            if any(_same_issue(key, issue_key) for key in keys) and (
                len(keys) > 1 or branch in local_tracker_malformed
            ):
                blockers.append(f"pull-request identity is conflicting: {branch}")

    if blockers:
        die(blockers[0])
    for branch in sorted(open_candidates):
        if branch not in refs:
            die(f"pull-request head is unavailable locally or remotely: {branch}")
    if len(open_candidates) > 1:
        die("multiple open pull-request heads identify the Issue: " + ", ".join(sorted(open_candidates)))
    if open_candidates:
        return next(iter(open_candidates))
    if len(branch_candidates) > 1:
        die("multiple existing branches identify the Issue: " + ", ".join(sorted(branch_candidates)))
    return next(iter(branch_candidates)) if branch_candidates else None


def prepare(
    repo_root: Path,
    issue_key: str,
    title: str | None = None,
    description: str = "",
    exclude_branches: set[str] | None = None,
) -> StartPlan:
    key = _issue_key(issue_key)
    script = _resolver_script(repo_root)
    context = _native(repo_root, script, key) if script else None
    if context is None and script is None and _configured(repo_root):
        die("Linear is configured but its installed work-item resolver is unavailable; reinstall the Linear extension")
    if context is None:
        if not isinstance(title, str) or not title.strip():
            die("Linear configuration is absent; provide the Issue title to derive the work-item branch")
        slug = _slug(title)
        if not slug:
            die("Issue title must contain letters or numbers to derive the work-item branch")
        context = WorkItemContext(key, title.strip(), description, f"{key.casefold()}-{slug}")
    refs = branch_refs(repo_root)
    prs = pull_requests(repo_root)
    observations = None
    excluded = exclude_branches or set()
    observed_branches = sorted(branch for branch in refs if branch not in excluded and not RESERVED_RE.fullmatch(branch))
    if context.configured and script and (observed_branches or prs):
        observations = _bridge_observations(repo_root, script, observed_branches, prs)
    adopted = _adopt(key, refs, prs, observations, observed_branches)
    if adopted is not None:
        return StartPlan(WorkItemContext(context.issue_key, context.title, context.description, adopted, context.url, context.configured), True, refs[adopted][1])
    _validate_branch(repo_root, context.branch_name)
    return StartPlan(context)

def start(
    repo_root: Path,
    issue_key: str,
    title: str | None = None,
    description: str = "",
) -> WorkItemContext:
    """Return native Issue context or derive an unconfigured default branch."""
    return prepare(repo_root, issue_key, title, description).context


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or len(values) > 2:
        die("usage: work_item_start.py <issue-key> [title]")
    context = start(Path.cwd(), values[0], values[1] if len(values) == 2 else None)
    print(json.dumps(asdict(context), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
