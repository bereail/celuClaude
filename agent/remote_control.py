"""Control remoto de mouse (Prioridad 3, alcance acotado): un tap en el
espejo de pantalla del celular mueve el mouse y hace click ahi. A proposito
NO incluye teclado ni drag/scroll -- ver docs/ARCHITECTURE.md para el
roadmap completo.

Como con el resto de las acciones del agente, esto reconfirma permisos de
forma local (nunca confia ciegamente en que el backend ya valido algo):
- remote_control_enabled en config.yaml es el interruptor maestro (analogo
  a screenshot_enabled) -- si esta en false, un backend comprometido no
  puede mover el mouse aunque lo pida.
- Ademas, el llamador (agent.py) solo invoca esto mientras streaming_active
  esta seteado -- no tiene sentido (y es peligroso) mover el mouse a ciegas,
  sin que haya una imagen real de la pantalla frente a alguien.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import mss
import pyautogui

pyautogui.FAILSAFE = True  # mover el mouse a una esquina lo aborta -- lo dejamos activo a proposito

AUDIT_LOG_PATH = Path(__file__).resolve().parent / "agent_audit.log"


def _audit(line: str) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{ts} {line}\n")
    except OSError:
        pass


def get_capture_monitor() -> dict:
    """El mismo monitor (indice y geometria) que screenshot_reporter usa para
    capturar -- el mapeo de coordenadas del click solo tiene sentido si
    coincide exactamente con lo que la imagen mostrada realmente representa."""
    with mss.mss() as sct:
        return sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]


def fractional_to_absolute(x_frac: float, y_frac: float, monitor: dict) -> tuple[int, int]:
    x_frac = min(max(x_frac, 0.0), 1.0)
    y_frac = min(max(y_frac, 0.0), 1.0)
    x = monitor["left"] + round(x_frac * monitor["width"])
    y = monitor["top"] + round(y_frac * monitor["height"])
    return x, y


class RemoteControlDisabled(Exception):
    pass


def click(x_frac: float, y_frac: float, button: str, cfg: dict) -> dict:
    if not cfg.get("remote_control_enabled"):
        raise RemoteControlDisabled("Control remoto deshabilitado en config.yaml del agente")
    if button not in ("left", "right"):
        button = "left"

    monitor = get_capture_monitor()
    x, y = fractional_to_absolute(x_frac, y_frac, monitor)
    pyautogui.moveTo(x, y)
    pyautogui.click(x, y, button=button)

    _audit(f"REMOTE_CLICK button={button} frac=({x_frac:.3f},{y_frac:.3f}) abs=({x},{y})")
    return {"x": x, "y": y, "button": button}
