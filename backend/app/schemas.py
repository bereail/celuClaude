from datetime import datetime

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ProjectIn(BaseModel):
    name: str
    path: str
    description: str = ""
    technologies: str = ""


class ProjectOut(ProjectIn):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class DeviceOut(BaseModel):
    id: str
    name: str
    os: str
    status: str
    last_seen: datetime | None
    cpu_percent: float
    ram_percent: float
    current_project: str

    class Config:
        from_attributes = True


class SessionCreate(BaseModel):
    project_id: str | None = None
    title: str = ""
    autonomy_level: int = 1


class SessionOut(BaseModel):
    id: str
    project_id: str | None
    title: str
    autonomy_level: int
    status: str
    started_at: datetime
    ended_at: datetime | None

    class Config:
        from_attributes = True


class InstructionIn(BaseModel):
    device_id: str
    text: str


class ApprovalDecisionIn(BaseModel):
    decision: str  # "approved" | "denied" | "always"


class ExplainRequest(BaseModel):
    question: str
