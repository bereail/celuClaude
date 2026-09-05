from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from ..auth import get_current_user
from ..database import get_db
from ..models import Device, Project
from ..schemas import DeviceOut, ProjectIn, ProjectOut

router = APIRouter(tags=["projects"], dependencies=[Depends(get_current_user)])


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: DBSession = Depends(get_db)):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectIn, db: DBSession = Depends(get_db)):
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, db: DBSession = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    db.delete(project)
    db.commit()
    return {"ok": True}


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(db: DBSession = Depends(get_db)):
    return db.query(Device).order_by(Device.created_at.desc()).all()
