"""Tool implementations that actually touch the filesystem/shell, plus a
local re-check of permissions (defense layer #2 — the backend already
classified the call, but the agent never trusts that blindly).

IMPORTANT — known residual risk (see docs/ARCHITECTURE.md "Auditoria"):
this local check confirms a command is on the agent's OWN allowlist or
confirm-list, but it does NOT verify that a human actually approved a
confirm-tier action — that proof currently lives only in the backend's
approval flow. If the backend process itself were compromised (not just
the network path to it, which per-device tokens now protect), it could
still ask the agent to run a confirm-tier command without a real approval
ever having happened on the phone. Closing that fully needs the phone to
sign approvals with a key the backend never holds — not implemented yet.
Every confirm-tier execution is written to agent_audit.log independently
of the backend's DB, so there is at least a local, backend-independent
record to check.
"""

from __future__ import annotations

import fnmatch
import os
import platform
import subprocess
from pathlib import Path

from audit import audit as _audit


class PermissionDenied(Exception):
    pass


def _path_denied(path: str, cfg: dict) -> bool:
    return any(fnmatch.fnmatch(path.lower(), pat.lower()) for pat in cfg["deny_path_patterns"])


def _is_within(path: Path, root: Path) -> bool:
    path_s = str(path).rstrip(os.sep).lower()
    root_s = str(root).rstrip(os.sep).lower()
    return path_s == root_s or path_s.startswith(root_s + os.sep)


def _path_within_roots(path: str, cfg: dict) -> bool:
    roots = cfg.get("allowed_roots") or []
    if not roots:
        return True
    try:
        p = Path(path).resolve()
    except OSError:
        return False
    return any(_is_within(p, Path(r).resolve()) for r in roots)


def _check_path(path: str, cfg: dict) -> None:
    if _path_denied(path, cfg):
        raise PermissionDenied(f"Ruta bloqueada por patron de seguridad: {path}")
    if not _path_within_roots(path, cfg):
        raise PermissionDenied(f"Ruta fuera de los directorios autorizados: {path}")


def list_dir(tool_input: dict, cfg: dict) -> dict:
    path = tool_input["path"]
    _check_path(path, cfg)
    p = Path(path)
    if not p.exists():
        return {"error": f"No existe: {path}"}
    entries = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
    return {"summary": f"{len(entries)} elementos", "entries": entries}


def read_file(tool_input: dict, cfg: dict) -> dict:
    path = tool_input["path"]
    _check_path(path, cfg)
    p = Path(path)
    if not p.exists() or not p.is_file():
        return {"error": f"No existe el archivo: {path}"}
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"error": str(exc)}
    truncated = content[:20000]
    return {"summary": f"{len(content)} caracteres leidos", "content": truncated}


def write_file(tool_input: dict, cfg: dict) -> dict:
    path = tool_input["path"]
    content = tool_input.get("content", "")
    _check_path(path, cfg)
    if len(content.encode("utf-8", errors="ignore")) > cfg["max_write_bytes"]:
        raise PermissionDenied("Escritura excede el tamaño maximo permitido.")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"summary": f"Escrito {path} ({len(content)} caracteres)"}


def _kill_tree_windows(pid: int) -> None:
    # subprocess.run(timeout=...) kills the immediate child on Windows but
    # does NOT kill its descendants (e.g. `npm run dev` -> node.exe keeps
    # running after the npm.cmd wrapper is gone). taskkill /T does a real
    # tree-kill. Best-effort: if it fails we've still killed the direct child.
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10)
    except Exception:
        pass


def run_command(tool_input: dict, cfg: dict) -> dict:
    command = tool_input["command"]
    cwd = tool_input.get("cwd") or None
    lowered = command.strip().lower()
    first_token = lowered.split(" ")[0] if lowered else ""
    is_confirm_tier = any(lowered.startswith(c) for c in cfg.get("confirm_commands", []))
    if first_token not in cfg["allowed_commands"] and not is_confirm_tier:
        raise PermissionDenied(f"Comando no permitido por config local del agente: {first_token}")
    if cwd:
        _check_path(cwd, cfg)

    if is_confirm_tier:
        _audit(f"CONFIRM-TIER EXEC command={command!r} cwd={cwd!r}")

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creationflags,
    )
    try:
        output, _ = proc.communicate(timeout=cfg.get("command_timeout_seconds", 120))
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        if platform.system() == "Windows":
            _kill_tree_windows(proc.pid)
        else:
            proc.kill()
        proc.communicate()
        _audit(f"TIMEOUT KILLED command={command!r} pid={proc.pid}")
        return {"error": "El comando excedio el tiempo maximo de ejecucion y fue terminado."}

    return {
        "summary": f"exit={returncode}",
        "returncode": returncode,
        "output": (output or "")[:20000],
    }


DISPATCH = {
    "list_dir": list_dir,
    "read_file": read_file,
    "write_file": write_file,
    "run_command": run_command,
}


def execute_tool(tool_name: str, tool_input: dict, cfg: dict) -> dict:
    handler = DISPATCH.get(tool_name)
    if not handler:
        _audit(f"UNKNOWN TOOL {tool_name!r}")
        return {"error": f"Herramienta desconocida: {tool_name}"}
    try:
        result = handler(tool_input, cfg)
        _audit(f"OK {tool_name} input={tool_input!r} -> {result.get('summary', result.get('error', ''))!r}")
        return result
    except PermissionDenied as exc:
        _audit(f"DENIED {tool_name} input={tool_input!r} reason={exc}")
        return {"error": str(exc)}
    except Exception as exc:  # nunca tirar la conexion del agente por un error de una tool
        _audit(f"EXCEPTION {tool_name} input={tool_input!r} error={exc}")
        return {"error": f"Error ejecutando {tool_name}: {exc}"}
