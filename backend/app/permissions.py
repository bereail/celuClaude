"""Permission engine: classifies a tool call Claude wants to run into
ALLOW / CONFIRM / DENY *before* it is ever sent to the PC agent.

This is defense layer #1 (backend). The agent (agent/executor.py) re-applies
an equivalent check locally as defense layer #2, so a compromised backend
still can't make the agent do arbitrary things.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from .models import ActionDecision

CONFIG_PATH = Path(__file__).resolve().parent.parent / "permissions.yaml"

_DEFAULT_CONFIG = {
    "allowed_roots": [],
    "allowed_commands": ["python", "pytest", "git", "npm", "node", "pip"],
    "confirm_commands": ["pip install", "npm install", "git push", "git commit", "rm", "del"],
    "deny_path_patterns": [
        "*.env", "*.env.*", "*password*", "*credentials*", "*.pem", "*.key",
        "*id_rsa*", "*cookies*", "*.pfx", "*wallet*",
    ],
    "max_write_bytes": 2_000_000,
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        merged = {**_DEFAULT_CONFIG, **data}
        return merged
    return dict(_DEFAULT_CONFIG)


@dataclass
class Verdict:
    decision: ActionDecision
    reason: str


def _path_is_denied(path: str, cfg: dict) -> bool:
    return any(fnmatch.fnmatch(path.lower(), pat.lower()) for pat in cfg["deny_path_patterns"])


def _is_within(path: Path, root: Path) -> bool:
    """True if `path` is `root` or a descendant of it. Plain startswith() on
    the string form is a classic bypass: 'D:\\GIT-secrets' startswith
    'D:\\GIT' too. Comparing full path segments avoids that."""
    path_s = str(path).rstrip(os.sep).lower()
    root_s = str(root).rstrip(os.sep).lower()
    return path_s == root_s or path_s.startswith(root_s + os.sep)


def _path_is_within_roots(path: str, cfg: dict) -> bool:
    roots = cfg.get("allowed_roots") or []
    if not roots:
        return True  # no roots configured -> not restricted by root (still filtered by deny patterns)
    try:
        p = Path(path).resolve()
    except OSError:
        return False
    return any(_is_within(p, Path(r).resolve()) for r in roots)


def classify(tool_name: str, tool_input: dict) -> Verdict:
    cfg = load_config()

    if tool_name in ("read_file", "write_file", "list_dir"):
        path = tool_input.get("path", "")
        if _path_is_denied(path, cfg):
            return Verdict(ActionDecision.DENY, f"'{path}' coincide con un patron prohibido (secretos/credenciales).")
        if not _path_is_within_roots(path, cfg):
            return Verdict(ActionDecision.DENY, f"'{path}' esta fuera de los directorios autorizados.")
        if tool_name == "write_file":
            content = tool_input.get("content", "")
            if len(content.encode("utf-8", errors="ignore")) > cfg["max_write_bytes"]:
                return Verdict(ActionDecision.CONFIRM, "Escritura inusualmente grande, requiere confirmacion.")
            return Verdict(ActionDecision.CONFIRM, f"Modificar '{path}'.")
        return Verdict(ActionDecision.ALLOW, "Lectura dentro de directorios autorizados.")

    if tool_name == "run_command":
        command = (tool_input.get("command") or "").strip()
        lowered = command.lower()
        if any(lowered.startswith(bad) for bad in cfg["confirm_commands"]):
            return Verdict(ActionDecision.CONFIRM, f"El comando '{command}' requiere confirmacion explicita.")
        first_token = lowered.split(" ")[0] if lowered else ""
        if first_token in cfg["allowed_commands"]:
            return Verdict(ActionDecision.ALLOW, "Comando en la allowlist.")
        return Verdict(ActionDecision.CONFIRM, f"'{first_token}' no esta en la allowlist, requiere confirmacion.")

    return Verdict(ActionDecision.CONFIRM, f"Herramienta desconocida '{tool_name}', requiere confirmacion.")


def record_standing_grant(db, tool_name: str, pattern: str) -> None:
    from .models import StandingPermission

    db.add(StandingPermission(tool_name=tool_name, pattern=pattern))
    db.commit()


def has_standing_grant(db, tool_name: str, candidate: str) -> bool:
    from .models import StandingPermission

    grants = db.query(StandingPermission).filter(StandingPermission.tool_name == tool_name).all()
    return any(fnmatch.fnmatch(candidate.lower(), g.pattern.lower()) for g in grants)
