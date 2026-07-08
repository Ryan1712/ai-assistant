import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.config import get_settings
from app.models import (
    Device, Invite, LoginEvent, RefreshToken, Role, User, UserStatus, Workspace,
)

_DUMMY_HASH = security.hash_password("dummy-timing-equalizer")


async def _issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    access = security.create_access_token(
        user_id=str(user.id), workspace_id=str(user.workspace_id), role=user.role.value,
    )
    plain, hashed = security.new_refresh_token()
    db.add(RefreshToken(
        workspace_id=user.workspace_id, user_id=user.id, token_hash=hashed,
        expires_at=datetime.now(timezone.utc) + timedelta(days=get_settings().refresh_ttl_days),
    ))
    return access, plain


async def _log_device(db: AsyncSession, user: User, device_uuid: str, device_name: str) -> None:
    now = datetime.now(timezone.utc)
    device = (await db.execute(
        select(Device).where(Device.user_id == user.id, Device.device_uuid == device_uuid)
    )).scalar_one_or_none()
    if device:
        device.device_name = device_name or device.device_name
        device.last_login_at = now
    else:
        db.add(Device(
            workspace_id=user.workspace_id, user_id=user.id,
            device_uuid=device_uuid, device_name=device_name, last_login_at=now,
        ))
    db.add(LoginEvent(
        workspace_id=user.workspace_id, user_id=user.id,
        device_uuid=device_uuid, device_name=device_name,
    ))


async def signup_workspace(
    db: AsyncSession, *, workspace_name: str, email: str, password: str,
    full_name: str, device_uuid: str, device_name: str,
) -> tuple[User, str, str]:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "email_taken")
    ws = Workspace(name=workspace_name)
    db.add(ws)
    await db.flush()
    user = User(
        workspace_id=ws.id, email=email, password_hash=security.hash_password(password),
        full_name=full_name, role=Role.ceo, is_root=True,
    )
    db.add(user)
    await db.flush()
    await _log_device(db, user, device_uuid, device_name)
    access, refresh = await _issue_tokens(db, user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "email_taken")
    return user, access, refresh


async def login(
    db: AsyncSession, *, email: str, password: str, device_uuid: str, device_name: str,
) -> tuple[User, str, str]:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not user:
        security.verify_password(password, _DUMMY_HASH)
        raise HTTPException(401, "invalid_credentials")
    if not security.verify_password(password, user.password_hash):
        raise HTTPException(401, "invalid_credentials")
    if user.status == UserStatus.locked:
        raise HTTPException(403, "account_locked")
    await _log_device(db, user, device_uuid, device_name)
    access, refresh = await _issue_tokens(db, user)
    await db.commit()
    return user, access, refresh


async def rotate_refresh(db: AsyncSession, refresh_plain: str) -> tuple[User, str, str]:
    now = datetime.now(timezone.utc)
    hashed = security.hash_refresh_token(refresh_plain)
    row = (await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hashed)
    )).scalar_one_or_none()
    if row is None or row.revoked_at is not None or row.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(401, "invalid_refresh_token")
    user = await db.get(User, row.user_id)
    if user is None or user.status == UserStatus.locked:
        raise HTTPException(403, "account_locked")
    row.revoked_at = now
    access, new_refresh = await _issue_tokens(db, user)
    await db.commit()
    return user, access, new_refresh


async def revoke_refresh(db: AsyncSession, refresh_plain: str) -> None:
    hashed = security.hash_refresh_token(refresh_plain)
    row = (await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hashed)
    )).scalar_one_or_none()
    if row and row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        await db.commit()


async def create_invite(
    db: AsyncSession, *, actor: User, role: str, manager_id=None,
) -> Invite:
    if actor.role != Role.ceo:
        raise HTTPException(403, "forbidden")
    role_enum = Role(role)
    if role_enum == Role.employee:
        manager = await db.get(User, manager_id) if manager_id else None
        if not manager or manager.role != Role.manager or manager.workspace_id != actor.workspace_id:
            raise HTTPException(422, "employee_invite_requires_manager")
    invite = Invite(
        workspace_id=actor.workspace_id, token=secrets.token_urlsafe(24),
        role=role_enum, manager_id=manager_id, created_by=actor.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invite)
    await db.commit()
    return invite


async def signup_invite(
    db: AsyncSession, *, token: str, email: str, password: str,
    full_name: str, device_uuid: str, device_name: str,
) -> tuple[User, str, str]:
    now = datetime.now(timezone.utc)
    invite = (await db.execute(select(Invite).where(Invite.token == token))).scalar_one_or_none()
    if (invite is None or invite.used_at is not None
            or invite.expires_at.replace(tzinfo=timezone.utc) < now):
        raise HTTPException(400, "invalid_invite")
    if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(409, "email_taken")
    user = User(
        workspace_id=invite.workspace_id, email=email,
        password_hash=security.hash_password(password), full_name=full_name,
        role=invite.role, manager_id=invite.manager_id,
    )
    db.add(user)
    await db.flush()
    invite.used_at = now
    await _log_device(db, user, device_uuid, device_name)
    access, refresh = await _issue_tokens(db, user)
    await db.commit()
    return user, access, refresh
