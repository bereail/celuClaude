"""Claude Command Center — agente local.

Corre en la PC, se conecta de forma saliente al backend por WebSocket
(nunca escucha en ningun puerto) y ejecuta las acciones que Claude pide,
re-validando permisos localmente antes de tocar el filesystem o una shell.

Uso:
    python agent.py
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import platform
import sys
from pathlib import Path

import psutil
import websockets
import yaml

from executor import execute_tool
from remote_control import RemoteControlDisabled, click as remote_click

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("Falta config.yaml. Copia config.example.yaml a config.yaml y completalo.")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_credentials(device_id: str, device_token: str) -> None:
    cfg = load_config()
    cfg["device_id"] = device_id
    cfg["device_token"] = device_token
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


async def authenticate(ws, cfg: dict) -> None:
    hello = {"type": "hello", "name": cfg["device_name"], "os": platform.system()}
    if cfg.get("device_id") and cfg.get("device_token"):
        hello["device_id"] = cfg["device_id"]
        hello["device_token"] = cfg["device_token"]
    else:
        hello["enrollment_token"] = cfg["enrollment_token"]

    await ws.send(json.dumps(hello))
    raw = await asyncio.wait_for(ws.recv(), timeout=10)
    reply = json.loads(raw)
    if reply.get("type") != "registered":
        raise ConnectionRefusedError(reply.get("detail", "Registro rechazado por el backend"))

    if reply.get("device_token"):
        save_credentials(reply["device_id"], reply["device_token"])
        cfg["device_id"] = reply["device_id"]
        cfg["device_token"] = reply["device_token"]
        print(f"[agent] nuevo device_id={reply['device_id']} — token guardado en config.yaml")
    else:
        print(f"[agent] reconectado como device_id={reply['device_id']}")


async def status_reporter(ws, cfg: dict):
    while True:
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "status",
                        "cpu_percent": psutil.cpu_percent(interval=None),
                        "ram_percent": psutil.virtual_memory().percent,
                        "current_project": cfg.get("current_project", ""),
                    }
                )
            )
        except websockets.exceptions.ConnectionClosed:
            return
        await asyncio.sleep(5)


async def screenshot_reporter(ws, cfg: dict, streaming_active: asyncio.Event):
    """Solo captura y manda cuadros mientras streaming_active esta seteado
    (alguien mirando la pantalla desde el celular) Y screenshot_enabled es
    true en la config (interruptor maestro, independiente de quien lo pida)."""
    if not cfg.get("screenshot_enabled"):
        return
    import hashlib

    import mss
    from PIL import Image

    interval = cfg.get("screenshot_interval_seconds", 0.4)
    max_width = cfg.get("screenshot_max_width", 900)
    quality = cfg.get("screenshot_quality", 55)
    last_hash: str | None = None

    with mss.mss() as sct:
        while True:
            await streaming_active.wait()
            try:
                raw = sct.grab(sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0])
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                if img.width > max_width:
                    ratio = max_width / img.width
                    img = img.resize((max_width, int(img.height * ratio)))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality)
                jpeg_bytes = buf.getvalue()

                frame_hash = hashlib.blake2b(jpeg_bytes, digest_size=8).hexdigest()
                if frame_hash != last_hash:
                    last_hash = frame_hash
                    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
                    await ws.send(json.dumps({"type": "screenshot", "image_b64": b64, "ts": asyncio.get_event_loop().time()}))
                # si la pantalla no cambio, no reenviamos el mismo cuadro --
                # ahorra ancho de banda sin perder "sensacion de en vivo"
            except websockets.exceptions.ConnectionClosed:
                return
            except Exception as exc:
                print(f"[screenshot] error: {exc}")
            await asyncio.sleep(interval)


async def handle_messages(ws, cfg: dict, streaming_active: asyncio.Event):
    async for raw in ws:
        msg = json.loads(raw)
        msg_type = msg.get("type")

        if msg_type == "execute":
            request_id = msg["request_id"]
            tool_name = msg["tool_name"]
            tool_input = msg["tool_input"]
            print(f"[agent] ejecutando {tool_name}({tool_input})")
            result = await asyncio.to_thread(execute_tool, tool_name, tool_input, cfg)
            await ws.send(json.dumps({"type": "result", "request_id": request_id, "result": result}))
            await ws.send(json.dumps({"type": "activity", "text": f"{tool_name} -> {result.get('summary', result.get('error', ''))}"}))

        elif msg_type == "screen_subscribe":
            streaming_active.set()
            print("[agent] espejo de pantalla: activado (alguien esta mirando)")

        elif msg_type == "screen_unsubscribe":
            streaming_active.clear()
            print("[agent] espejo de pantalla: pausado (nadie esta mirando)")

        elif msg_type == "remote_click":
            # Nunca mover el mouse a ciegas: solo mientras alguien esta
            # efectivamente mirando el espejo de pantalla en este momento.
            if not streaming_active.is_set():
                continue
            try:
                result = remote_click(msg.get("x", 0.5), msg.get("y", 0.5), msg.get("button", "left"), cfg)
                await ws.send(json.dumps({"type": "activity", "text": f"click remoto ({result['button']}) en ({result['x']},{result['y']})"}))
            except RemoteControlDisabled as exc:
                print(f"[agent] click remoto rechazado: {exc}")
            except Exception as exc:
                print(f"[agent] error en click remoto: {exc}")


async def run():
    cfg = load_config()
    backoff = 2
    while True:
        try:
            print(f"[agent] conectando a {cfg['server_url']}/ws/agent ...")
            async with websockets.connect(f"{cfg['server_url'].rstrip('/')}/ws/agent", max_size=20 * 1024 * 1024) as ws:
                await authenticate(ws, cfg)
                backoff = 2
                streaming_active = asyncio.Event()  # arranca "nadie mirando"
                await asyncio.gather(
                    handle_messages(ws, cfg, streaming_active),
                    status_reporter(ws, cfg),
                    screenshot_reporter(ws, cfg, streaming_active),
                )
        except (websockets.exceptions.ConnectionClosed, OSError, ConnectionRefusedError, asyncio.TimeoutError) as exc:
            print(f"[agent] conexion perdida/rechazada ({exc}); reintentando en {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    asyncio.run(run())
