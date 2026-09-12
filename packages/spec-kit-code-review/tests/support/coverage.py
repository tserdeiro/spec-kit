from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


def coverage_for_session(repository, session_path: str | Path) -> dict:
    session_dir = Path(session_path)
    session = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    inventory = json.loads((session_dir / "context-inventory.json").read_text(encoding="utf-8"))
    reads = []
    for required in inventory.get("required", []):
        path = required["path"]
        version = next(source["version"] for source in inventory.get("sources", []) if source["path"] == path)
        if path == "<pull-request-intent>":
            intent = session.get("pr_intent") or {}
            raw = (str(intent.get("title", "")) + "\n" + str(intent.get("body", ""))).encode("utf-8")
        else:
            raw = subprocess.run(
                ["git", "-C", str(repository.path), "cat-file", "blob", f"{session['head_commit']}:{path}"],
                check=True, capture_output=True,
            ).stdout
        lines = raw.splitlines(keepends=True)
        start, end = int(required["start"]), int(required["end"])
        selected = b"".join(lines[start - 1 : end])
        reads.append({"path": path, "version": version, "start_line": start, "end_line": end,
                      "sha256": hashlib.sha256(selected).hexdigest(),
                      "assessment": "test fixture reviewed the required context", "scope": "test"})
    return {"candidate_id": session["candidate_id"], "packet_sha256": session["packet_sha256"],
            "inventory_sha256": session["packet"]["inventory_sha256"], "reads": reads}
