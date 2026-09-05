"""Modo EXPLAIN: responde preguntas sobre UNA accion puntual ya ejecutada
(que hizo, por que, que significa, como explicarlo en una entrevista).

A proposito NO tiene acceso a herramientas -- es una llamada de solo lectura
a Claude, no puede tocar el filesystem ni ejecutar nada en el agente. Por
diseño no puede haber una autorizacion CONFIRM/DENY que sortear: preguntar
"que hiciste" nunca puede convertirse en una accion real sobre la PC.
"""

from __future__ import annotations

from sqlalchemy.orm import Session as DBSession

from .claude_orchestrator import client, emit_message, settings
from .models import ActionLog, Message

EXPLAIN_SYSTEM_PROMPT = (
    "Sos un profesor de programacion. Te dan el detalle tecnico de UNA accion puntual que "
    "Claude Command Center ya ejecuto en la computadora de un desarrollador (que herramienta, "
    "con que datos, que resultado dio), mas el contexto de la conversacion donde paso. Tu unico "
    "trabajo es EXPLICAR, en espanol rioplatense y lenguaje simple -- nunca sugieras ni describas "
    "comandos nuevos para ejecutar, no sos parte del flujo de accion, sos un profesor mirando algo "
    "que ya paso. Si preguntan como explicarlo en una entrevista tecnica, dales una respuesta corta "
    "que puedan memorizar y decir en voz alta con confianza. Usa ejemplos concretos del "
    "codigo/comando real cuando ayude. Se conciso, esto se lee en un celular."
)

MAX_CONTEXT_MESSAGES = 6


async def explain_action(db: DBSession, action: ActionLog, question: str) -> str:
    context_messages = (
        db.query(Message)
        .filter(Message.session_id == action.session_id)
        .order_by(Message.created_at.desc())
        .limit(MAX_CONTEXT_MESSAGES)
        .all()
    )
    context_messages.reverse()
    conversation_context = "\n".join(f"[{m.role}] {m.content}" for m in context_messages) or "(sin contexto previo)"

    action_block = (
        f"Herramienta ejecutada: {action.tool_name}\n"
        f"Datos de entrada: {action.tool_input}\n"
        f"Decision del sistema de permisos: {action.decision} (estado final: {action.status})\n"
        f"Resultado: {(action.result or '')[:4000]}"
    )

    prompt = (
        f"Contexto de la conversacion (ultimos mensajes):\n{conversation_context}\n\n"
        f"Accion puntual sobre la que preguntan:\n{action_block}\n\n"
        f"Pregunta del usuario: {question}"
    )

    response = await client.messages.create(
        model=settings.claude_model,
        max_tokens=700,
        system=EXPLAIN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    answer = "\n".join(block.text for block in response.content if block.type == "text").strip()
    answer = answer or "No pude generar una explicacion para esto."

    await emit_message(action.session_id, "user", f"🎓 [Explicar: {action.tool_name}] {question}", db)
    await emit_message(action.session_id, "assistant", answer, db)

    return answer
