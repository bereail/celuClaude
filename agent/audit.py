"""Audit log local del agente, compartido por executor.py y
remote_control.py -- registro best-effort e independiente del backend (ver
docs/ARCHITECTURE.md "Auditoria")."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

AUDIT_LOG_PATH = Path(__file__).resolve().parent / "agent_audit.log"


def audit(line: str) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{ts} {line}\n")
    except OSError:
        pass  # el audit log local es best-effort, nunca debe tumbar al agente
