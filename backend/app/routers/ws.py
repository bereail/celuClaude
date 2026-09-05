import asyncio
import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from passlib.context import CryptContext
from sqlalchemy.orm import Session as DBSession

from ..auth import decode_token
from ..config import get_settings
from ..database import SessionLocal
from ..models import Device
from ..ws_manager import hub

router = APIRouter()
settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

AUTH_TIMEOUT_SECONDS = 10


@router.websocket("/ws/mobile")
async def mobile_ws(websocket: WebSocket):
    """Auth happens over the first message, not the URL, so a JWT never ends
    up in a proxy/access log line (query strings do, message bodies don't)."""

    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
        msg = json.loads(raw)
        if msg.get("type") != "auth":
            raise ValueError("Primer mensaje debe ser {type: 'auth', token: ...}")
        payload = decode_token(msg["token"])
        if payload.get("type") != "access":
            raise ValueError("Tipo de token incorrecto")
    except Exception:
        await websocket.close(code=4401)
        return

    user_id = payload["sub"]
    hub.register_mobile(user_id, websocket)
    await websocket.send_text(json.dumps({"type": "authenticated"}))
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue  # keepalive pings u otro texto no-JSON, se ignoran

            msg_type = msg.get("type")
            device_id = msg.get("device_id")
            if msg_type == "screen_subscribe" and device_id:
                if hub.subscribe_screen(device_id, user_id):
                    try:
                        await hub.send_to_agent(device_id, {"type": "screen_subscribe"})
                    except ConnectionError:
                        pass  # el agente no esta online, no hay a quien avisar
            elif msg_type == "screen_unsubscribe" and device_id:
                if hub.unsubscribe_screen(device_id, user_id):
                    try:
                        await hub.send_to_agent(device_id, {"type": "screen_unsubscribe"})
                    except ConnectionError:
                        pass
            elif msg_type == "remote_click" and device_id:
                # Solo se puede clickear un dispositivo cuya pantalla se esta
                # mirando en este momento -- nunca a ciegas.
                if user_id not in hub.screen_subscribers.get(device_id, set()):
                    continue
                try:
                    await hub.send_to_agent(
                        device_id,
                        {
                            "type": "remote_click",
                            "x": float(msg.get("x", 0.5)),
                            "y": float(msg.get("y", 0.5)),
                            "button": msg.get("button", "left"),
                        },
                    )
                except (ConnectionError, TypeError, ValueError):
                    pass
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        hub.unregister_mobile(user_id)
        for device_id in hub.unsubscribe_screen_everywhere(user_id):
            try:
                await hub.send_to_agent(device_id, {"type": "screen_unsubscribe"})
            except ConnectionError:
                pass


def _issue_device_token() -> tuple[str, str]:
    plain = secrets.token_urlsafe(32)
    return plain, pwd_context.hash(plain)


@router.websocket("/ws/agent")
async def agent_ws(websocket: WebSocket):
    """Registration/reconnection handshake, also over the first message:

    First connection for a PC:
        -> {"type": "hello", "enrollment_token": "...", "name": "...", "os": "..."}
        <- {"type": "registered", "device_id": "...", "device_token": "..."}
           (agent persists device_id + device_token locally; from then on it
           reconnects with those instead of the shared enrollment_token)

    Reconnection:
        -> {"type": "hello", "device_id": "...", "device_token": "...", "name": "...", "os": "..."}
        <- {"type": "registered", "device_id": "..."}

    The shared enrollment_token only ever proves "this caller is allowed to
    enroll a NEW device"; it can't be used to hijack or impersonate a device
    that already has its own token, which is what closes the gap where any
    client could previously claim an existing device_id with no proof.
    """

    await websocket.accept()
    db = SessionLocal()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
        hello = json.loads(raw)
        if hello.get("type") != "hello":
            raise ValueError("Primer mensaje debe ser {type: 'hello', ...}")

        name = hello.get("name", "")
        os_name = hello.get("os", "")
        device_id = hello.get("device_id")
        device_token = hello.get("device_token")
        issued_token: str | None = None

        if device_id and device_token:
            device = db.get(Device, device_id)
            if not device or not device.token_hash or not pwd_context.verify(device_token, device.token_hash):
                raise ValueError("device_id/device_token invalido")
        elif hello.get("enrollment_token") == settings.agent_enrollment_token:
            issued_token, token_hash = _issue_device_token()
            device = Device(name=name or "PC sin nombre", os=os_name, token_hash=token_hash)
            db.add(device)
            db.commit()
            db.refresh(device)
        else:
            raise ValueError("Credenciales de agente invalidas")
    except Exception as exc:
        try:
            await websocket.send_text(json.dumps({"type": "error", "detail": str(exc)}))
        finally:
            await websocket.close(code=4403)
        db.close()
        return

    device.name = name or device.name
    device.os = os_name or device.os
    device.status = "online"
    device.last_seen = datetime.now(timezone.utc)
    db.commit()
    db.refresh(device)

    hub.register_agent(device.id, websocket)
    response = {"type": "registered", "device_id": device.id}
    if issued_token:
        response["device_token"] = issued_token
    await websocket.send_text(json.dumps(response))
    await hub.broadcast_to_mobile({"type": "device_status", "device_id": device.id, "status": "online"})

    # Si habia gente mirando la pantalla de esta PC cuando el agente se
    # desconecto, retomamos el streaming apenas vuelve a conectarse.
    if hub.screen_subscribers.get(device.id):
        await websocket.send_text(json.dumps({"type": "screen_subscribe"}))

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "result":
                hub.resolve_agent_call(msg["request_id"], msg.get("result", {}))

            elif msg_type == "status":
                device.cpu_percent = msg.get("cpu_percent", device.cpu_percent)
                device.ram_percent = msg.get("ram_percent", device.ram_percent)
                device.current_project = msg.get("current_project", device.current_project)
                device.last_seen = datetime.now(timezone.utc)
                db.commit()
                await hub.broadcast_to_mobile({"type": "device_status", "device_id": device.id, **msg})

            elif msg_type == "screenshot":
                await hub.broadcast_to_mobile(
                    {"type": "screenshot", "device_id": device.id, "image_b64": msg.get("image_b64"), "ts": msg.get("ts")}
                )

            elif msg_type == "activity":
                await hub.broadcast_to_mobile({"type": "activity", "device_id": device.id, "text": msg.get("text", "")})

    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        # device.id se guarda ANTES de commit/close: el commit expira los
        # atributos del objeto (expire_on_commit=True por defecto), y leer
        # device.id despues de cerrar la sesion tira DetachedInstanceError
        # -- eso hacia que este aviso de "device offline" nunca le llegara
        # a los celulares conectados.
        device_id = device.id
        hub.unregister_agent(device_id)
        device.status = "offline"
        device.last_seen = datetime.now(timezone.utc)
        db.commit()
        db.close()
        await hub.broadcast_to_mobile({"type": "device_status", "device_id": device_id, "status": "offline"})
