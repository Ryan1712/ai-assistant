import datetime as dt
import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models import ChatRequestStatus, Role, SkillKind, TaskPriority, TaskStatus, WorkspacePlan


class SignupWorkspaceIn(BaseModel):
    workspace_name: str
    email: EmailStr
    password: str
    full_name: str
    device_uuid: str
    device_name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    device_uuid: str
    device_name: str = ""


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_root: bool

    model_config = {"from_attributes": True}


class DeviceOut(BaseModel):
    device_uuid: str
    device_name: str
    last_login_at: dt.datetime

    model_config = {"from_attributes": True}


class AuthOut(BaseModel):
    access_token: str
    refresh_token: str
    user: UserOut


class RefreshIn(BaseModel):
    refresh_token: str


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str


class InviteCreateIn(BaseModel):
    role: Role
    manager_id: uuid.UUID | None = None


class InviteOut(BaseModel):
    token: str
    expires_at: dt.datetime


class SignupCodeIn(BaseModel):
    invite_code: str
    email: EmailStr
    password: str
    full_name: str
    device_uuid: str
    device_name: str = ""


class SignupInviteIn(BaseModel):
    token: str
    email: EmailStr
    password: str
    full_name: str
    device_uuid: str
    device_name: str = ""


class UnlockRequestIn(BaseModel):
    email: EmailStr
    device_uuid: str


class ProjectCreateIn(BaseModel):
    name: str
    goal: str = ""
    deadline: dt.datetime | None = None
    owner_id: uuid.UUID | None = None


class ProjectPatchIn(BaseModel):
    name: str | None = None
    goal: str | None = None
    status: str | None = None
    deadline: dt.datetime | None = None
    owner_id: uuid.UUID | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    goal: str
    status: str
    deadline: dt.datetime | None
    owner_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class TaskCreateIn(BaseModel):
    project_id: uuid.UUID
    title: str
    description: str = ""
    deadline: dt.datetime | None = None
    priority: TaskPriority = TaskPriority.medium


class TaskPatchIn(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    percent: int | None = Field(None, ge=0, le=100)
    deadline: dt.datetime | None = None
    priority: TaskPriority | None = None


class TaskOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str
    status: TaskStatus
    percent: int
    deadline: dt.datetime | None
    priority: TaskPriority
    assignee_ids: list[uuid.UUID] = []


class AssigneeIn(BaseModel):
    user_id: uuid.UUID


class TaskUpdateCreateIn(BaseModel):
    content: str = ""
    percent: int | None = Field(None, ge=0, le=100)
    status: TaskStatus | None = None


class TaskUpdateOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    author_id: uuid.UUID
    content: str
    percent: int | None
    status: TaskStatus | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class CommentCreateIn(BaseModel):
    content: str


class CommentOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    author_id: uuid.UUID
    content: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class SkillCreateIn(BaseModel):
    name: str
    kind: SkillKind
    task_id: uuid.UUID | None = None
    content: str


class SkillVersionIn(BaseModel):
    content: str


class SkillGrantIn(BaseModel):
    user_id: uuid.UUID


class SkillOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: SkillKind
    task_id: uuid.UUID | None
    latest_version: int


class TaskUpdateSummaryOut(BaseModel):
    author_id: str
    content: str
    percent: int | None
    created_at: str


class TaskStateOut(BaseModel):
    id: str
    title: str
    status: str
    percent: int
    deadline: str | None
    priority: str
    assignees: list[str]
    latest_updates: list[TaskUpdateSummaryOut]


class UseSkillOut(BaseModel):
    skill_id: str
    name: str
    kind: str
    version: int
    content: str
    task_state: TaskStateOut | None


class SubscriptionPatchIn(BaseModel):
    plan: WorkspacePlan


class SubscriptionOut(BaseModel):
    plan: str
    limits: dict[str, int] | None


class NoteCreateIn(BaseModel):
    content: str
    tags: list[str] = []
    note_date: dt.date | None = None
    task_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


class NoteOut(BaseModel):
    id: uuid.UUID
    content: str
    tags: list[str]
    note_date: dt.date
    task_id: uuid.UUID | None
    project_id: uuid.UUID | None


class InstructionCreateIn(BaseModel):
    title: str
    content: str


class InstructionUpdateIn(BaseModel):
    content: str


class InstructionOut(BaseModel):
    id: uuid.UUID
    title: str
    version: int
    content: str


class ConversationCreateIn(BaseModel):
    title: str | None = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class MessageSendIn(BaseModel):
    content: str


class ChatRequestOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: ChatRequestStatus
    content: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class ConfirmIn(BaseModel):
    approved: bool


class ChatRequestEditIn(BaseModel):
    content: str


class ReorderIn(BaseModel):
    before_id: uuid.UUID | None = None
