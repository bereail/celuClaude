import anthropic
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from ..auth import get_current_user
from ..claude_orchestrator import run_instruction
from ..database import SessionLocal, get_db
from ..explain import explain_action
from ..models import ActionLog, Message, Project, Session as SessionModel
from ..schemas import ApprovalDecisionIn, ExplainRequest, InstructionIn, SessionCreate, SessionOut
from ..ws_manager import hub

router = APIRouter(tags=["sessions"], dependencies=[Depends(get_current_user)])


@router.post("/sessions", response_model=SessionOut)
def create_session(payload: SessionCreate, db: DBSession = Depends(get_db)):
    session = SessionModel(**payload.model_dump())
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(db: DBSession = Depends(get_db)):
    return db.query(SessionModel).order_by(SessionModel.started_at.desc()).all()


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str, db: DBSession = Depends(get_db)):
    msgs = db.query(Message).filter(Message.session_id == session_id).order_by(Message.created_at).all()
    return [{"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at} for m in msgs]


@router.get("/sessions/{session_id}/actions")
def get_actions(session_id: str, db: DBSession = Depends(get_db)):
    actions = db.query(ActionLog).filter(ActionLog.session_id == session_id).order_by(ActionLog.created_at).all()
    return [
        {
            "id": a.id,
            "tool_name": a.tool_name,
            "tool_input": a.tool_input,
            "decision": a.decision,
            "status": a.status,
            "result": a.result,
            "created_at": a.created_at,
        }
        for a in actions
    ]


async def _run_in_background(session_id: str, device_id: str, project_path: str, text: str):
    db = SessionLocal()
    try:
        await run_instruction(db, session_id, device_id, project_path, text)
    finally:
        db.close()
        hub.mark_free(device_id)


@router.post("/sessions/{session_id}/instruct")
def send_instruction(session_id: str, payload: InstructionIn, background_tasks: BackgroundTasks, db: DBSession = Depends(get_db)):
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sesion no encontrada")
    if not hub.is_agent_online(payload.device_id):
        raise HTTPException(status_code=409, detail="El agente de la PC no esta conectado")
    if hub.is_device_busy(payload.device_id):
        raise HTTPException(status_code=409, detail="Claude ya esta ejecutando una instruccion en esa PC, esperá a que termine.")

    project_path = ""
    if session.project_id:
        project = db.get(Project, session.project_id)
        project_path = project.path if project else ""

    # Marcado sincronico, antes de encolar la tarea, para cerrar la ventana de
    # carrera entre dos POST /instruct casi simultaneos contra el mismo device.
    hub.mark_busy(payload.device_id)
    background_tasks.add_task(_run_in_background, session_id, payload.device_id, project_path, payload.text)
    return {"accepted": True}


@router.post("/actions/{action_id}/decision")
def decide_action(action_id: str, payload: ApprovalDecisionIn, db: DBSession = Depends(get_db)):
    if payload.decision not in ("approved", "denied", "always"):
        raise HTTPException(status_code=400, detail="Decision invalida")
    action = db.get(ActionLog, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Accion no encontrada")
    if action.status != "pending":
        raise HTTPException(status_code=409, detail=f"Esta accion ya fue resuelta (status={action.status}).")
    if not hub.resolve_approval(action_id, payload.decision):
        raise HTTPException(
            status_code=409,
            detail="No hay una espera activa para esta accion (probablemente el backend se reinicio mientras esperaba). Reintentá la instruccion.",
        )
    return {"ok": True}


@router.post("/actions/{action_id}/explain")
async def explain(action_id: str, payload: ExplainRequest, db: DBSession = Depends(get_db)):
    action = db.get(ActionLog, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Accion no encontrada")
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacia")
    try:
        answer = await explain_action(db, action, payload.question.strip())
    except anthropic.APIError as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo consultar a Claude: {exc.__class__.__name__}")
    return {"answer": answer}
