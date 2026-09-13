"""Diagnosis and safe native registration of the commit message check."""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .errors import AppError, Diagnostic
from .git import Git


HOOK_NAME = "speckit-commit-message"
HOOK_EVENT = "commit-msg"
HOOK_COMMAND = "sh .specify/extensions/code-review/scripts/bash/commit-msg.sh"
MIN_NATIVE_GIT = (2, 54)
PAYLOAD = (
    Path(".specify/extensions/code-review/scripts/bash/commit-msg.sh"),
    Path(".specify/extensions/code-review/src/spec_kit_code_review/__init__.py"),
    Path(".specify/extensions/code-review/src/spec_kit_code_review/commit_msg.py"),
    Path(".specify/extensions/code-review/src/spec_kit_code_review/commit_policy.py"),
)


@dataclass(frozen=True)
class HookRecord:
    scope: str
    origin: str
    key: str
    value: str


@dataclass
class HookObservation:
    """The effective facts used by both diagnosis and a repair transaction."""

    root: Path
    git: Git
    config_path: Path | None = None
    config_scope: str = "local"
    hooks_path: Path | None = None
    config_snapshot: _ConfigSnapshot | None = None
    traditional_hook_snapshot: tuple[object, ...] = ()
    records: list[HookRecord] = field(default_factory=list)
    listed: list[tuple[str, bool]] = field(default_factory=list)
    list_ok: bool = False
    list_error: str = ""
    git_version: tuple[int, ...] = ()
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def own(self) -> list[HookRecord]:
        prefix = f"hook.{HOOK_NAME}."
        return [record for record in self.records if record.key.startswith(prefix)]

    @property
    def state(self) -> str:
        own = self.own
        if not self.list_ok and not self._event_only_list_failure:
            return "unverifiable"
        if self._disabled:
            return "disabled"
        if self.duplicate:
            return "duplicate"
        if any(record.scope != self.config_scope for record in own):
            return "foreign"
        if any(not _origin_matches(record.origin, self.config_path, self.root) for record in own):
            return "foreign"
        commands = self._values("command")
        events = self._values("event")
        if not own:
            return "missing"
        if any(value != HOOK_COMMAND for value in commands):
            return "conflict"
        if HOOK_EVENT not in events:
            return "partial"
        if not self.list_ok:
            return "partial"
        if any(name == HOOK_NAME and not disabled for name, disabled in self.listed):
            return "installed" if len(commands) == 1 and events == [HOOK_EVENT] else "partial"
        return "unverifiable"

    @property
    def _event_only_list_failure(self) -> bool:
        """Git 2.54 rejects ``hook list`` when an event has no command."""

        message = self.list_error.lower()
        return (
            not self.list_ok
            and not self._values("command")
            and HOOK_EVENT in self._values("event")
            and "must be configured" in message
            and "command" in message
        )

    @property
    def duplicate(self) -> bool:
        return any(
            str(PAYLOAD[0]) in record.value and not record.key.startswith(f"hook.{HOOK_NAME}.")
            for record in self.records
        ) or _manual_hook_invocation(self.hooks_path)

    @property
    def _disabled(self) -> bool:
        values = [record.value.lower() for record in self.records if record.key == f"hook.{HOOK_NAME}.enabled"]
        event_values = [record.value.lower() for record in self.records if record.key == f"hook.{HOOK_EVENT}.enabled"]
        return (values and values[-1] in {"", "false", "no", "off", "0"}) or (
            event_values and event_values[-1] in {"", "false", "no", "off", "0"}
        ) or any(name == HOOK_NAME and disabled for name, disabled in self.listed)

    def _values(self, field_name: str) -> list[str]:
        return [record.value for record in self.own if record.key == f"hook.{HOOK_NAME}.{field_name}"]

    @property
    def signature(self) -> tuple[object, ...]:
        return (
            self.config_path,
            self.config_scope,
            self.config_snapshot,
            self.hooks_path,
            self.traditional_hook_snapshot,
            tuple((r.scope, r.origin, r.key, r.value) for r in self.records),
            tuple(self.listed),
            self.list_ok,
        )


@dataclass(frozen=True)
class HookRepair:
    applied: str | None = None
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class _ConfigSnapshot:
    exists: bool
    mode: int | None
    bytes: bytes
    is_regular: bool
    is_symlink: bool
    device: int
    inode: int
    parent_device: int
    parent_inode: int
    parent_is_directory: bool
    parent_mode: int
    parent_is_symlink: bool


def observe_native_hook(root: Path, git: Git) -> HookObservation:
    """Read Git's effective hook arrangement without executing consumer hooks."""

    observation = HookObservation(root=root.resolve(), git=git)
    try:
        observation.git_version = git.version().parts
    except AppError as error:
        observation.diagnostics.append(Diagnostic("git_hooks_unverifiable", f"could not read Git version: {error}"))
        return observation

    hooks_result = git.run("rev-parse", "--path-format=absolute", "--git-path", "hooks/commit-msg")
    if hooks_result.ok:
        observation.hooks_path = _absolute_path(hooks_result.stdout.strip())
    else:
        observation.diagnostics.append(
            Diagnostic("git_hooks_path_unreadable", "could not resolve Git's effective hooks path", str(root))
        )
    observation.traditional_hook_snapshot = _traditional_hook_snapshot(observation.hooks_path)

    worktree_result = git.run("config", "--local", "--bool", "--get", "extensions.worktreeConfig")
    worktree_config = worktree_result.ok and worktree_result.stdout.strip().lower() in {"true", "yes", "on", "1"}
    observation.config_scope = "worktree" if worktree_config else "local"
    config_name = "config.worktree" if worktree_config else "config"
    config_result = git.run("rev-parse", "--path-format=absolute", "--git-path", config_name)
    if not config_result.ok:
        observation.diagnostics.append(
            Diagnostic("git_hooks_config_unreadable", f"could not resolve Git's {config_name} path", str(root))
        )
    else:
        resolved_config = _absolute_path(config_result.stdout.strip())
        lexical_config = _lexical_config_path(git, observation.config_scope, config_name)
        observation.config_path = lexical_config if lexical_config is not None and lexical_config.is_symlink() else resolved_config
        try:
            observation.config_snapshot = _config_snapshot(observation.config_path)
        except OSError as error:
            observation.diagnostics.append(
                Diagnostic("git_hooks_config_unreadable", f"could not inspect Git configuration: {error}", str(observation.config_path))
            )
        if observation.config_snapshot is not None and not observation.config_snapshot.is_regular:
            observation.diagnostics.append(
                Diagnostic("git_hooks_config_unreadable", "Git configuration is not a regular file", str(observation.config_path))
            )

    config_result = git.run("config", "--null", "--show-origin", "--show-scope", "--get-regexp", r"^hook\.")
    if config_result.ok or config_result.returncode == 1:
        observation.records = _parse_records(config_result.stdout)
    else:
        observation.diagnostics.append(
            Diagnostic("git_hooks_config_unverifiable", "Git could not read effective hook configuration", str(root))
        )

    if observation.git_version < MIN_NATIVE_GIT:
        observation.list_error = ", ".join(str(part) for part in observation.git_version)
        return observation

    listed = git.run("hook", "list", "-z", "--show-scope", HOOK_EVENT)
    observation.list_ok = listed.returncode in (0, 1)
    observation.list_error = listed.stderr.strip()
    if observation.list_ok:
        observation.listed = _parse_hook_list(listed.stdout)
    elif not observation._event_only_list_failure:
        observation.diagnostics.append(
            Diagnostic("git_hooks_capability_unavailable", listed.stderr.strip() or "`git hook list` failed", str(root))
        )
    return observation


def hook_diagnostics(root: Path, git: Git) -> list[Diagnostic]:
    """Return concise, actionable findings for the current arrangement."""

    observation = observe_native_hook(root, git)
    diagnostics = list(observation.diagnostics)
    if observation.hooks_path is not None:
        diagnostics.append(Diagnostic("git_hooks_path", f"effective commit-msg hooks path: {observation.hooks_path}", str(observation.hooks_path), severity="info"))
    if observation.config_path is not None:
        diagnostics.append(Diagnostic("git_hooks_config_scope", f"native registration scope: {observation.config_scope} ({observation.config_path})", str(observation.config_path), severity="info"))
        if observation.config_path.is_symlink():
            diagnostics.append(Diagnostic("git_hooks_unsafe_config", "native registration uses a symlinked Git configuration destination; preserve it and integrate the hook manually", str(observation.config_path), severity="error"))
            return diagnostics
    if observation.git_version < MIN_NATIVE_GIT:
        diagnostics.append(
            Diagnostic(
                "git_hooks_upgrade",
                f"native commit-msg registration needs Git >= 2.54; found {'.'.join(map(str, observation.git_version))}. Upgrade Git, then run `doctor --fix`",
                str(root),
                severity="error",
            )
        )
        return diagnostics
    state = observation.state
    if state == "installed":
        diagnostics.append(Diagnostic("git_hooks_installed", f"{HOOK_NAME} validates commit-msg through Git's named hook list", str(observation.config_path), severity="info"))
        payload_roots = _payload_roots(observation)
        if payload_roots is None:
            diagnostics.append(Diagnostic("git_hooks_worktree_unverifiable", "could not enumerate linked worktrees; inspect them before enabling shared validation", str(observation.root), severity="error"))
            return diagnostics
        payload = [diagnostic for path in payload_roots for diagnostic in _payload_diagnostics(path)]
        diagnostics.extend(payload)
    elif state == "missing":
        diagnostics.append(Diagnostic("git_hooks_missing", f"native commit-msg validation is missing; run `doctor --fix` to register {HOOK_NAME}", str(observation.hooks_path or observation.root), severity="warning"))
    elif state == "partial":
        diagnostics.append(Diagnostic("git_hooks_partial", f"{HOOK_NAME} is incomplete; run `doctor --fix` to normalize its local entry", str(observation.config_path), severity="warning"))
    elif state == "disabled":
        disabled = next((record for record in observation.records if record.key in {f"hook.{HOOK_NAME}.enabled", f"hook.{HOOK_EVENT}.enabled"} and record.value.lower() in {"", "false", "no", "off", "0"}), None)
        origin = f" at {disabled.origin} ({disabled.scope} scope)" if disabled else ""
        diagnostics.append(Diagnostic("git_hooks_disabled", f"{HOOK_NAME} or the commit-msg event is disabled{origin}; enable it explicitly before running `doctor --fix`", str(observation.config_path), severity="error"))
    elif state == "foreign":
        foreign = next((record for record in observation.own if record.scope != observation.config_scope or not _origin_matches(record.origin, observation.config_path, observation.root)), None)
        location = f" at {foreign.origin} ({foreign.scope} scope)" if foreign else ""
        diagnostics.append(Diagnostic("git_hooks_foreign_scope", f"{HOOK_NAME} is configured outside the selected {observation.config_scope} scope{location}; integrate it manually", str(observation.config_path), severity="error"))
    elif state == "conflict":
        diagnostics.append(Diagnostic("git_hooks_name_conflict", f"{HOOK_NAME} has a different command; preserve it and choose another name or repair it manually", str(observation.config_path), severity="error"))
    elif state == "duplicate":
        diagnostics.append(Diagnostic("git_hooks_duplicate", f"another native entry or traditional hook invokes the validator; remove the duplicate manually before running `doctor --fix`", str(observation.hooks_path or observation.config_path), severity="error"))
    else:
        diagnostics.append(Diagnostic("git_hooks_unverifiable", "native commit-msg validation could not be verified; inspect Git configuration and retry", str(observation.root), severity="error"))
    return diagnostics


def install_native_hook(root: Path, git: Git) -> HookRepair:
    """Converge one owned local/worktree entry under Git's config lock."""

    observation = observe_native_hook(root, git)
    if observation.git_version < MIN_NATIVE_GIT:
        return HookRepair(diagnostics=(Diagnostic("git_hooks_upgrade", "upgrade Git to >= 2.54, then run `doctor --fix`", str(root)),))
    if observation.diagnostics or observation.config_path is None or observation.config_snapshot is None or observation.config_snapshot.is_symlink or observation.state in {"disabled", "foreign", "conflict", "duplicate", "unverifiable"}:
        return HookRepair(diagnostics=tuple(hook_diagnostics(root, git)))
    payloads = _payload_roots(observation)
    if payloads is None:
        return HookRepair(diagnostics=(Diagnostic("git_hooks_worktree_unverifiable", "could not enumerate linked worktrees; no shared config was changed", str(observation.root)),))
    payload = [diagnostic for path in payloads for diagnostic in _payload_diagnostics(path)]
    if payload:
        return HookRepair(diagnostics=tuple(payload))
    if observation.state == "installed":
        return HookRepair()
    diagnosed_snapshot = observation.config_snapshot
    if diagnosed_snapshot.is_symlink or not diagnosed_snapshot.parent_is_directory or diagnosed_snapshot.parent_is_symlink:
        return HookRepair(diagnostics=(Diagnostic("git_hooks_unsafe_config", "refusing an ambiguous or symlinked Git configuration destination; integrate the hook manually", str(observation.config_path)),))
    writable = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    if diagnosed_snapshot.exists and not diagnosed_snapshot.mode & writable:
        return HookRepair(diagnostics=(Diagnostic("git_hooks_config_read_only", "Git configuration is read-only; restore its owner write bit and retry doctor", str(observation.config_path)),))
    if not diagnosed_snapshot.parent_mode & writable:
        return HookRepair(diagnostics=(Diagnostic("git_hooks_config_directory_read_only", "Git configuration directory is read-only; restore its owner write bit and retry doctor", str(observation.config_path.parent)),))

    lock = observation.config_path.with_name(observation.config_path.name + ".lock")
    lock_identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError as error:
        return HookRepair(diagnostics=(Diagnostic("git_hooks_config_locked", f"could not acquire the exclusive Git config lock: {error}; retry after the lock is gone", str(lock)),))
    lock_status = os.fstat(descriptor)
    lock_identity = (lock_status.st_dev, lock_status.st_ino)
    os.close(descriptor)
    temporary: Path | None = None
    temporary_identity: tuple[int, int] | None = None
    try:
        try:
            current_snapshot = _config_snapshot(observation.config_path)
        except OSError as error:
            return HookRepair(diagnostics=(Diagnostic("git_hooks_stale_snapshot", f"could not re-read Git config under lock: {error}; retry", str(observation.config_path)),))
        if current_snapshot != diagnosed_snapshot:
            return HookRepair(diagnostics=(Diagnostic("git_hooks_stale_snapshot", "Git configuration changed after diagnosis; no hook changes were made, retry doctor", str(observation.config_path)),))
        fresh = observe_native_hook(root, git)
        if fresh.signature != observation.signature:
            return HookRepair(diagnostics=(Diagnostic("git_hooks_stale_snapshot", "effective hook configuration changed after diagnosis; no hook changes were made, retry doctor", str(observation.config_path)),))

        with tempfile.NamedTemporaryFile(prefix=f".{observation.config_path.name}.speckit-", dir=observation.config_path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(diagnosed_snapshot.bytes)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_status = temporary.lstat()
        temporary_identity = (temporary_status.st_dev, temporary_status.st_ino)
        mode = diagnosed_snapshot.mode if diagnosed_snapshot.exists and diagnosed_snapshot.mode is not None else 0o644
        temporary.chmod(mode)
        command = git.run("config", "set", "--file", str(temporary), "--all", f"hook.{HOOK_NAME}.command", HOOK_COMMAND)
        if not command.ok:
            return HookRepair(diagnostics=(Diagnostic("git_hooks_temp_config_failed", command.stderr.strip() or "Git could not edit the temporary configuration", str(temporary)),))
        if observation._values("event"):
            unset = git.run("config", "unset", "--file", str(temporary), "--all", f"hook.{HOOK_NAME}.event")
            if not unset.ok:
                return HookRepair(diagnostics=(Diagnostic("git_hooks_temp_config_failed", unset.stderr.strip() or "Git could not normalize the temporary hook events", str(temporary)),))
        event = git.run("config", "set", "--file", str(temporary), f"hook.{HOOK_NAME}.event", HOOK_EVENT)
        if not event.ok:
            return HookRepair(diagnostics=(Diagnostic("git_hooks_temp_config_failed", event.stderr.strip() or "Git could not set the temporary hook event", str(temporary)),))
        verify = git.run("config", "--file", str(temporary), "--get-all", f"hook.{HOOK_NAME}.command")
        events = git.run("config", "--file", str(temporary), "--get-all", f"hook.{HOOK_NAME}.event")
        if not verify.ok or verify.stdout.splitlines() != [HOOK_COMMAND] or not events.ok or events.stdout.splitlines() != [HOOK_EVENT]:
            return HookRepair(diagnostics=(Diagnostic("git_hooks_temp_config_failed", "Git's edited configuration did not contain exactly one owned command and event", str(temporary)),))
        replacement_bytes = temporary.read_bytes()
        replacement_status = temporary.lstat()
        temporary_identity = (replacement_status.st_dev, replacement_status.st_ino)
        replacement_mode = stat.S_IMODE(replacement_status.st_mode)
        late_observation = observe_native_hook(root, git)
        if late_observation.signature != observation.signature:
            return HookRepair(diagnostics=(Diagnostic("git_hooks_stale_snapshot", "effective hook configuration changed while preparing the repair; no hook changes were made, retry doctor", str(observation.config_path)),))
        try:
            late_snapshot = _config_snapshot(observation.config_path)
        except OSError as error:
            return HookRepair(diagnostics=(Diagnostic("git_hooks_stale_snapshot", f"could not re-read Git config immediately before replacement: {error}; no hook changes were made, retry", str(observation.config_path)),))
        if late_snapshot != diagnosed_snapshot:
            return HookRepair(diagnostics=(Diagnostic("git_hooks_stale_snapshot", "Git configuration changed while preparing the repair; no hook changes were made, retry doctor", str(observation.config_path)),))
        expected_replacement = _ConfigSnapshot(
            True,
            replacement_mode,
            replacement_bytes,
            True,
            False,
            replacement_status.st_dev,
            replacement_status.st_ino,
            diagnosed_snapshot.parent_device,
            diagnosed_snapshot.parent_inode,
            diagnosed_snapshot.parent_is_directory,
            diagnosed_snapshot.parent_mode,
            diagnosed_snapshot.parent_is_symlink,
        )
        os.replace(temporary, observation.config_path)
        temporary = None
        final = observe_native_hook(root, git)
        if final.state != "installed":
            restored, recovery = _restore_config(observation.config_path, diagnosed_snapshot, expected_replacement)
            if restored:
                message = "native registration was written but Git could not verify it; restored the diagnosed config and mode, inspect it and retry doctor"
            else:
                message = f"native registration was written but Git could not verify it; restoration was not applied ({recovery}), inspect the config manually and use the owned-section rollback before retrying"
            return HookRepair(diagnostics=(Diagnostic("git_hooks_readback_failed", message, str(observation.config_path)),))
        return HookRepair(applied=f"registered {HOOK_NAME} for {HOOK_EVENT} in {observation.config_scope} Git config")
    except OSError as error:
        return HookRepair(diagnostics=(Diagnostic("git_hooks_write_failed", f"native registration was not completed: {error}; retry doctor", str(observation.config_path)),))
    finally:
        if temporary is not None:
            try:
                current_parent = temporary.parent.lstat()
                current_temporary = temporary.lstat()
                if (
                    (current_parent.st_dev, current_parent.st_ino)
                    == (diagnosed_snapshot.parent_device, diagnosed_snapshot.parent_inode)
                    and temporary_identity == (current_temporary.st_dev, current_temporary.st_ino)
                ):
                    temporary.unlink()
            except OSError:
                pass
        if lock_identity is not None:
            try:
                current_lock = lock.lstat()
                if (current_lock.st_dev, current_lock.st_ino) == lock_identity:
                    lock.unlink()
            except OSError:
                pass


def _parse_records(text: str) -> list[HookRecord]:
    records: list[HookRecord] = []
    fields = text.split("\0")
    for index in range(0, len(fields) - 2, 3):
        scope, origin, key_value = fields[index : index + 3]
        key, separator, value = key_value.partition("\n")
        if not separator:
            continue
        if key.startswith("hook."):
            records.append(HookRecord(scope, origin, key, value))
    return records


def _parse_hook_list(output: str) -> list[tuple[str, bool]]:
    result: list[tuple[str, bool]] = []
    for entry in output.split("\0"):
        if not entry:
            continue
        parts = entry.split("\t")
        if len(parts) == 2:
            result.append((parts[1], False))
        elif len(parts) == 3:
            result.append((parts[2], parts[1] in {"disabled", "event-disabled"}))
    return result


def _absolute_path(value: str) -> Path:
    """Make Git's absolute path usable without resolving symlink targets."""

    return Path(os.path.abspath(value))


def _lexical_config_path(git: Git, scope: str, name: str) -> Path | None:
    """Recover a config path without Git's ``--git-path`` symlink resolution."""

    directory = "--git-dir" if scope == "worktree" else "--git-common-dir"
    result = git.run("rev-parse", "--path-format=absolute", directory)
    if not result.ok:
        return None
    return Path(os.path.abspath(result.stdout.strip())) / name


def _origin_matches(origin: str, target: Path | None, root: Path) -> bool:
    if target is None or not origin.startswith("file:"):
        return False
    source = origin[5:]
    return _absolute_path(source if os.path.isabs(source) else str(root / source)) == target


def _manual_hook_invocation(hooks_path: Path | None) -> bool:
    if hooks_path is None:
        return False
    try:
        hook = hooks_path
        if not hook.is_file():
            return False
        return any(str(PAYLOAD[0]) in line.split("#", 1)[0] for line in hook.read_text(encoding="utf-8", errors="ignore").splitlines())
    except OSError:
        return False


def _traditional_hook_snapshot(hooks_path: Path | None) -> tuple[object, ...]:
    """Capture the conventional dispatcher without following a changed path."""

    if hooks_path is None:
        return ("unresolved",)
    try:
        link_status = hooks_path.lstat()
        link = os.readlink(hooks_path) if stat.S_ISLNK(link_status.st_mode) else ""
        target_status = (target := hooks_path.resolve(strict=True) if link else hooks_path).lstat()
        contents = target.read_bytes() if stat.S_ISREG(target_status.st_mode) else b""
        return (
            stat.S_IFMT(link_status.st_mode), stat.S_IMODE(link_status.st_mode), link, str(target), target_status.st_dev,
            target_status.st_ino, stat.S_IFMT(target_status.st_mode), stat.S_IMODE(target_status.st_mode), contents,
        )
    except FileNotFoundError:
        return ("absent",)
    except OSError as error:
        return ("unreadable", type(error).__name__, str(error))


def _payload_diagnostics(root: Path) -> list[Diagnostic]:
    for relative in PAYLOAD:
        path = root / relative
        try:
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode) or not os.access(path, os.R_OK):
                return [Diagnostic("git_hooks_payload_unreadable", f"installed validator payload {relative} is not a readable regular file; reinstall the code-review extension", str(path))]
        except OSError:
            return [Diagnostic("git_hooks_payload_missing", f"installed validator payload {relative} is missing; reinstall the code-review extension, then run `doctor --fix`", str(path))]
    return []


def _payload_roots(observation: HookObservation) -> list[Path] | None:
    if observation.config_scope == "worktree":
        return [observation.root]
    result = observation.git.run("worktree", "list", "--porcelain")
    if not result.ok:
        return None
    roots = [Path(line[9:]).resolve() for line in result.stdout.splitlines() if line.startswith("worktree ")]
    return list(dict.fromkeys(roots or [observation.root]))


def _config_snapshot(path: Path) -> _ConfigSnapshot:
    parent = path.parent.lstat()
    try:
        current = path.lstat()
    except FileNotFoundError:
        return _ConfigSnapshot(
            False,
            None,
            b"",
            True,
            False,
            0,
            0,
            parent.st_dev,
            parent.st_ino,
            stat.S_ISDIR(parent.st_mode),
            stat.S_IMODE(parent.st_mode),
            stat.S_ISLNK(parent.st_mode),
        )
    is_symlink = stat.S_ISLNK(current.st_mode)
    is_regular = stat.S_ISREG(current.st_mode)
    return _ConfigSnapshot(
        True,
        stat.S_IMODE(current.st_mode),
        path.read_bytes() if is_regular else b"",
        is_regular,
        is_symlink,
        current.st_dev,
        current.st_ino,
        parent.st_dev,
        parent.st_ino,
        stat.S_ISDIR(parent.st_mode),
        stat.S_IMODE(parent.st_mode),
        stat.S_ISLNK(parent.st_mode),
    )


def _restore_config(path: Path, original: _ConfigSnapshot, expected: _ConfigSnapshot) -> tuple[bool, str]:
    try:
        current = _config_snapshot(path)
    except OSError as error:
        return False, f"could not inspect the destination: {error}"
    if current != expected:
        return False, "the destination or its parent changed after replacement; it was left untouched"
    if not original.exists:
        try:
            path.unlink()
        except OSError as error:
            return False, f"could not remove the newly created config: {error}"
        return True, ""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.name}.speckit-restore-", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(original.bytes)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(original.mode or 0o644)
        try:
            current = _config_snapshot(path)
        except OSError as error:
            return False, f"could not recheck the destination before restoration: {error}"
        if current != expected:
            return False, "the destination or its parent changed during restoration; it was left untouched"
        os.replace(temporary, path)
        temporary = None
        return True, ""
    except OSError as error:
        return False, f"could not restore the diagnosed config: {error}"
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
