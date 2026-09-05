"""Bridges a user instruction to Claude (tool use) and Claude's tool calls
to the PC agent, enforcing permissions.classify() on every single call and
streaming activity events to the mobile client as it goes.
"""

from __future__ import annotations

import json
import uuid

try:
    # En PCs con antivirus/EDR corporativo que hace inspeccion TLS, la lista
    # publica de CAs que trae httpx por defecto (certifi) no conoce la CA
    # raiz que ese software inyecta a nivel de sistema operativo, y las
    # llamadas a la API de Anthropic fallan con CERTIFICATE_VERIFY_FAILED
    # aunque la conexion sea legitima. truststore hace que Python valide
    # contra el almacen de certificados del SO en lugar de la lista de
    # certifi — sigue verificando TLS, solo cambia contra que lista.
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

import anthropic
from sqlalchemy.orm import Session as DBSession

from .config import get_settings
from .models import ActionDecision, ActionLog, ActionStatus, Message
from .permissions import classify, has_standing_grant, record_standing_grant
from .ws_manager import hub

settings = get_settings()
_extra_headers = {"anthropic-workspace-id": settings.anthropic_workspace_id} if settings.anthropic_workspace_id else {}
client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, default_headers=_extra_headers or None)

TOOLS = [
    {
        "name": "list_dir",
        "description": "Lista archivos y carpetas dentro de un directorio autorizado del proyecto.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo de texto dentro de un directorio autorizado.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Crea o sobreescribe un archivo de texto dentro de un directorio autorizado.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_command",
        "description": (
            "Ejecuta un comando de shell (python, pytest, git, npm, etc.) que TERMINA SOLO "
            "(un test, un build, un git status). NO uses esta herramienta para levantar servidores "
            "o procesos de larga duracion (npm run dev, un servidor de desarrollo, un watcher): "
            "el comando se corta a la fuerza a los pocos minutos y el proceso se mata, no queda corriendo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}, "cwd": {"type": "string"}},
            "required": ["command"],
        },
    },
]

SYSTEM_PROMPT = (
    "Sos el motor de Claude Command Center, un agente que ayuda a un desarrollador a trabajar "
    "en sus proyectos ejecutando acciones reales en su computadora a traves de herramientas. "
    "Explicá brevemente en texto plano (para mostrar en un celular) qué vas a hacer antes de "
    "usar una herramienta, y al final resumí qué hiciste, qué encontraste y qué modificaste. "
    "Respondé siempre en español rioplatense, de forma concisa."
)


async def emit_message(session_id: str, role: str, content: str, db: DBSession) -> None:
    db.add(Message(session_id=session_id, role=role, content=content))
    db.commit()
    await hub.broadcast_to_mobile({"type": "message", "session_id": session_id, "role": role, "content": content})


async def _emit_activity(session_id: str, text: str) -> None:
    await hub.broadcast_to_mobile({"type": "activity", "session_id": session_id, "text": text})


async def _dispatch_tool(
    db: DBSession, session_id: str, device_id: str, tool_name: str, tool_input: dict
) -> tuple[str, dict]:
    """Returns (status_text, result_payload) after enforcing permissions."""

    verdict = classify(tool_name, tool_input)
    candidate = tool_input.get("path") or tool_input.get("command", "")

    decision = verdict.decision
    if decision == ActionDecision.CONFIRM and has_standing_grant(db, tool_name, candidate):
        decision = ActionDecision.ALLOW

    action = ActionLog(
        session_id=session_id,
        device_id=device_id,
        tool_name=tool_name,
        tool_input=json.dumps(tool_input, ensure_ascii=False),
        decision=decision.value,
        reason=verdict.reason,
        status=ActionStatus.PENDING.value,
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    if decision == ActionDecision.DENY:
        action.status = ActionStatus.DENIED.value
        action.result = verdict.reason
        db.commit()
        await _emit_activity(session_id, f"🚫 Denegado: {tool_name}({candidate}) — {verdict.reason}")
        return "denied", {"error": verdict.reason}

    if decision == ActionDecision.CONFIRM:
        await _emit_activity(session_id, f"⚠️ Esperando autorizacion: {tool_name}({candidate})")
        await hub.broadcast_to_mobile(
            {
                "type": "authorization_required",
                "action_id": action.id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "reason": verdict.reason,
                "session_id": session_id,
            }
        )
        try:
            resolution = await hub.wait_for_approval(action.id)
        except TimeoutError:
            action.status = ActionStatus.DENIED.value
            action.result = "Timeout esperando autorizacion"
            db.commit()
            return "denied", {"error": "Timeout esperando autorizacion del usuario"}

        if resolution == "denied":
            action.status = ActionStatus.DENIED.value
            db.commit()
            await _emit_activity(session_id, f"🚫 Usuario denegó: {tool_name}({candidate})")
            return "denied", {"error": "El usuario denego la accion"}

        if resolution == "always":
            record_standing_grant(db, tool_name, candidate)

        action.status = ActionStatus.APPROVED.value
        db.commit()
        await _emit_activity(session_id, f"✅ Autorizado: {tool_name}({candidate})")

    # ALLOW (either directly or after approval)
    if not hub.is_agent_online(device_id):
        action.status = ActionStatus.FAILED.value
        action.result = "Agente desconectado"
        db.commit()
        return "failed", {"error": "El agente de la PC no esta conectado"}

    await _emit_activity(session_id, f"⚙️ Ejecutando: {tool_name}({candidate})")
    request_id = uuid.uuid4().hex
    try:
        result = await hub.call_agent(
            device_id, request_id, {"type": "execute", "request_id": request_id, "tool_name": tool_name, "tool_input": tool_input}
        )
    except (ConnectionError, TimeoutError) as exc:
        action.status = ActionStatus.FAILED.value
        action.result = str(exc)
        db.commit()
        return "failed", {"error": str(exc)}

    action.status = ActionStatus.EXECUTED.value
    action.result = json.dumps(result, ensure_ascii=False)[:8000]
    db.commit()
    await _emit_activity(session_id, f"✔️ Resultado: {tool_name} -> {str(result.get('summary', 'ok'))[:200]}")
    return "ok", result


async def run_instruction(db: DBSession, session_id: str, device_id: str, project_path: str, user_text: str) -> None:
    await emit_message(session_id, "user", user_text, db)

    history = db.query(Message).filter(Message.session_id == session_id).order_by(Message.created_at).all()
    messages = [
        {"role": "user" if m.role == "user" else "assistant", "content": m.content}
        for m in history
        if m.role in ("user", "assistant")
    ]

    context_note = f"\n\n(Directorio del proyecto activo: {project_path})" if project_path else ""
    if messages:
        messages[-1] = {**messages[-1], "content": messages[-1]["content"] + context_note}

    try:
        for _ in range(20):  # hard cap on tool-use turns per instruction
            response = await client.messages.create(
                model=settings.claude_model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            assistant_blocks = []
            text_out = []
            for block in response.content:
                if block.type == "text":
                    text_out.append(block.text)
                    assistant_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_blocks.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})

            if text_out:
                await emit_message(session_id, "assistant", "\n".join(text_out), db)

            messages.append({"role": "assistant", "content": assistant_blocks})

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in assistant_blocks:
                if block["type"] != "tool_use":
                    continue
                _, result = await _dispatch_tool(db, session_id, device_id, block["name"], block["input"])
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block["id"], "content": json.dumps(result, ensure_ascii=False)[:4000]}
                )

            messages.append({"role": "user", "content": tool_results})
    except anthropic.APIError as exc:
        await emit_message(
            session_id,
            "assistant",
            f"⚠️ Se cortó la comunicación con Claude a mitad de la tarea ({exc.__class__.__name__}). "
            "No se perdió nada de lo ya ejecutado — podés reintentar la instrucción.",
            db,
        )
    except Exception as exc:  # nunca dejar la sesion "trabajando" para siempre por un bug no previsto
        await emit_message(session_id, "assistant", f"⚠️ Error interno inesperado: {exc}", db)
    finally:
        await hub.broadcast_to_mobile({"type": "done", "session_id": session_id})
