#!/usr/bin/env python3
"""skill-mirror: mirror extension/preset skills across installed agents.

Direct translation of doctor.md step 5's shell block: copies every
non-core skill whole from the default integration's directory into each
lagging one, and appends the preset's registered layer to each lagging
integration's own core-command renders -- never a core skill copied
whole, never one integration's render overwritten by another's.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from _common import die

_ENTRY_RE = re.compile(r"^[ \t]*- type:")
_SKILL_RE = re.compile(r"/(speckit-[^/]*)/SKILL\.md$")

def _quoted(key: str, line: str) -> str | None:
    match = re.search(rf'{key}:\s*"([^"]*)"', line)
    return match.group(1) if match else None

def _registered_appends(repo_root: Path) -> dict[str, Path]:
    """speckit-x name -> its registered append file (relative to
    repo_root), first match wins, across every installed preset's
    preset.yml -- a direct translation of the block's own awk state
    machine over that YAML shape, one flush per "- type:" list entry."""
    appends: dict[str, Path] = {}
    for preset_yml in sorted((repo_root / ".specify/presets").glob("*/preset.yml")):
        preset_dir = preset_yml.parent.relative_to(repo_root)
        kind, name, file, strategy = "", "", "", ""
        lines = [*preset_yml.read_text(encoding="utf-8").splitlines(), "- type:"]
        for line in lines:
            if _ENTRY_RE.match(line):
                if kind == "command" and strategy == "append" and name and file:
                    appends.setdefault(re.sub(r"^speckit\.", "speckit-", name), preset_dir / file)
                kind = "command" if '"command"' in line else ""
                name, file, strategy = "", "", ""
                continue
            if kind != "command":
                continue
            name = _quoted("name", line) or name
            file = _quoted("file", line) or file
            strategy = _quoted("strategy", line) or strategy
    return appends

def _manifest_skills(manifest: Path) -> list[str]:
    """Every "*/speckit-*/SKILL.md" path in a manifest's files, in order."""
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [path for path in data.get("files", {}) if _SKILL_RE.search(path)]

def _skills_dir(paths: list[str]) -> str:
    return _SKILL_RE.sub("", paths[0]) if paths else ""

def mirror_skills(repo_root: Path, fix: bool) -> int:
    options = json.loads((repo_root / ".specify/init-options.json").read_text(encoding="utf-8"))
    default_ai = options.get("ai", "")
    integration = json.loads((repo_root / ".specify/integration.json").read_text(encoding="utf-8"))
    installed = integration.get("installed_integrations", [])
    if len(installed) <= 1:
        print("mirror: only one integration installed, skipped")
        return 0

    appends = _registered_appends(repo_root)
    integrations_dir = repo_root / ".specify/integrations"
    default_dir = _skills_dir(_manifest_skills(integrations_dir / f"{default_ai}.manifest.json"))
    if not default_dir:
        print(f"mirror: default integration {default_ai} has no skills to mirror")
        return 0

    acted = False
    for key in installed:
        if key == default_ai:
            continue
        paths = _manifest_skills(integrations_dir / f"{key}.manifest.json")
        lag_dir = _skills_dir(paths)
        if not lag_dir:
            print(f"mirror: {key} is command-mode, no skills to mirror")
            continue
        core = [_SKILL_RE.search(path).group(1) for path in paths]  # _manifest_skills already filtered

        for src in sorted((repo_root / default_dir).glob("speckit-*")):
            if not src.is_dir() or src.name in core:
                continue
            dst = repo_root / lag_dir / src.name
            dst_skill = dst / "SKILL.md"
            if dst_skill.is_file() and (src / "SKILL.md").read_bytes() == dst_skill.read_bytes():
                continue
            acted = True
            if fix:
                shutil.copytree(src, dst, dirs_exist_ok=True)
                print(f"mirror: copied {src.name} into {lag_dir} ({key})")
            else:
                print(f"mirror: {src.name} missing or differs in {lag_dir} ({key}) -- run with --fix")

        for name in core:
            append_file = appends.get(name)
            if append_file is None:
                continue
            render = repo_root / lag_dir / name / "SKILL.md"
            if not render.is_file():
                acted = True
                print(f"mirror: {name} missing in {lag_dir} ({key}) -- run: specify integration install {key}")
                continue
            full_append = repo_root / append_file
            if full_append.is_file():
                append_text = full_append.read_text(encoding="utf-8")
                heading = next((line for line in append_text.splitlines() if line.startswith("## ")), "")
            else:
                heading = ""
            if not heading:
                print(f"mirror: append {append_file} for {name} is missing or has no heading", file=sys.stderr)
                return 2
            render_text = render.read_text(encoding="utf-8")
            lines = render_text.splitlines()
            index = next((i for i, line in enumerate(lines) if line == heading), len(lines))
            prefix = "\n".join(lines[:index]).rstrip("\n")
            body = append_text.rstrip("\n")
            expected = f"{prefix}\n\n\n{body}"
            if render_text.rstrip("\n") == expected:
                continue
            acted = True
            if fix:
                render.write_text(f"{expected}\n", encoding="utf-8")
                print(f"mirror: appended the preset layer to {name} in {lag_dir} ({key})")
            else:
                print(f"mirror: {name} in {lag_dir} ({key}) needs the preset append -- run with --fix")

    if not acted:
        print("mirror: nothing to do")
    return 0

def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("true", "false"):
        die("usage: skill_mirror.py <true|false>")
    return mirror_skills(Path.cwd(), argv[0] == "true")

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
