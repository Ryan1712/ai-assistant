import datetime as dt
import uuid

from pydantic import BaseModel, EmailStr


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
    role: str  # "ceo" | "manager" | "employee"
    manager_id: uuid.UUID | None = None


class InviteOut(BaseModel):
    token: str
    expires_at: dt.datetime


class SignupInviteIn(BaseModel):
    token: str
    email: EmailStr
    password: str
    full_name: str
    device_uuid: str
    device_name: str = ""
