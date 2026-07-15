import secrets
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import plans, security
from app.config import get_settings
from app.models import (
    Device, Invite, LoginEvent, Notification, Project, RefreshToken, Role, TaskAssignee,
    User, UserStatus, Workspace,
)
from app.permissions import require_ceo
from app.services.notify import notify

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
    email = email.strip().lower()
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
    email = email.strip().lower()
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
    claimed = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == row.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    if claimed.rowcount != 1:
        raise HTTPException(401, "invalid_refresh_token")
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
    await plans.enforce_limit(db, actor.workspace_id, "members")
    role_enum = Role(role)
    if role_enum == Role.employee and manager_id is None:
        raise HTTPException(422, "employee_invite_requires_manager")
    if manager_id is not None:
        manager = await db.get(User, manager_id)
        if not manager or manager.role != Role.manager or manager.workspace_id != actor.workspace_id:
            raise HTTPException(422, "invalid_manager")
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
    email = email.strip().lower()
    now = datetime.now(timezone.utc)
    invite = (await db.execute(select(Invite).where(Invite.token == token))).scalar_one_or_none()
    if (invite is None or invite.used_at is not None
            or invite.expires_at.replace(tzinfo=timezone.utc) < now):
        raise HTTPException(400, "invalid_invite")
    if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(409, "email_taken")
    claimed = await db.execute(
        update(Invite)
        .where(Invite.id == invite.id, Invite.used_at.is_(None))
        .values(used_at=now)
    )
    if claimed.rowcount != 1:
        raise HTTPException(400, "invalid_invite")
    user = User(
        workspace_id=invite.workspace_id, email=email,
        password_hash=security.hash_password(password), full_name=full_name,
        role=invite.role, manager_id=invite.manager_id,
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


async def signup_with_code(
    db: AsyncSession, *, invite_code: str, email: str, password: str,
    full_name: str, device_uuid: str, device_name: str,
) -> tuple[User, str, str]:
    """Self sign-up bằng mã mời chung của workspace (funtional-plan 6.1).
    Luôn tạo employee, manager_id=None — CEO gán manager sau."""
    email = email.strip().lower()
    ws = (await db.execute(
        select(Workspace).where(Workspace.invite_code == invite_code)
    )).scalar_one_or_none()
    if ws is None:
        raise HTTPException(404, "invalid_invite_code")
    await plans.enforce_limit(db, ws.id, "members")
    if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(409, "email_taken")
    user = User(
        workspace_id=ws.id, email=email,
        password_hash=security.hash_password(password), full_name=full_name,
        role=Role.employee, manager_id=None,
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


async def get_invite_code(db: AsyncSession, actor: User) -> str:
    require_ceo(actor)
    ws = await db.get(Workspace, actor.workspace_id)
    return ws.invite_code


async def rotate_invite_code(db: AsyncSession, actor: User) -> str:
    require_ceo(actor)
    from app.models import _invite_code as _gen
    ws = await db.get(Workspace, actor.workspace_id)
    ws.invite_code = _gen()
    await db.commit()
    return ws.invite_code


def _check_lock_permission(actor: User, target: User) -> None:
    require_ceo(actor)
    if target.workspace_id != actor.workspace_id:
        raise HTTPException(404, "user_not_found")
    if target.is_root:
        raise HTTPException(403, "cannot_lock_root_ceo")
    if target.role == Role.ceo and not actor.is_root:
        raise HTTPException(403, "only_root_can_lock_ceo")


async def lock_user(db: AsyncSession, actor: User, target_id: uuid_mod.UUID) -> None:
    target = await db.get(User, target_id)
    if target is None:
        raise HTTPException(404, "user_not_found")
    _check_lock_permission(actor, target)
    target.status = UserStatus.locked
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == target.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await notify(db, workspace_id=target.workspace_id, recipient_id=target.id,
                 type="account_locked", payload={"by": str(actor.id)})
    await db.commit()


async def unlock_user(db: AsyncSession, actor: User, target_id: uuid_mod.UUID) -> None:
    target = await db.get(User, target_id)
    if target is None:
        raise HTTPException(404, "user_not_found")
    _check_lock_permission(actor, target)
    target.status = UserStatus.active
    await db.commit()


async def offboard_user(db: AsyncSession, actor: User, target_id: uuid_mod.UUID,
                        successor_id: uuid_mod.UUID | None = None) -> dict:
    await lock_user(db, actor, target_id)

    tasks_reassigned = 0
    projects_reassigned = 0
    reports_reassigned = 0

    if successor_id is not None:
        successor = await db.get(User, successor_id)
        if successor is None or successor.workspace_id != actor.workspace_id:
            raise HTTPException(404, "user_not_found")
        if successor.id == target_id or successor.status == UserStatus.locked:
            raise HTTPException(422, "invalid_successor")

        rows = (await db.execute(
            select(TaskAssignee).where(
                TaskAssignee.user_id == target_id,
                TaskAssignee.workspace_id == actor.workspace_id))).scalars().all()
        for row in rows:
            existing = await db.execute(select(TaskAssignee.id).where(
                TaskAssignee.task_id == row.task_id, TaskAssignee.user_id == successor_id,
                TaskAssignee.workspace_id == actor.workspace_id))
            if existing.first() is None:
                db.add(TaskAssignee(workspace_id=actor.workspace_id, task_id=row.task_id,
                                    user_id=successor_id))
            await db.delete(row)
            tasks_reassigned += 1

        result = await db.execute(update(Project).where(
            Project.workspace_id == actor.workspace_id, Project.owner_id == target_id
        ).values(owner_id=successor_id))
        projects_reassigned = result.rowcount or 0

        result = await db.execute(update(User).where(
            User.workspace_id == actor.workspace_id, User.manager_id == target_id,
            User.id != successor_id,
        ).values(manager_id=successor_id))
        reports_reassigned = result.rowcount or 0

        await notify(db, workspace_id=actor.workspace_id, recipient_id=successor_id,
                    type="offboard_handoff",
                    payload={"from_user": str(target_id), "tasks_reassigned": tasks_reassigned,
                             "projects_reassigned": projects_reassigned,
                             "reports_reassigned": reports_reassigned})
        await db.commit()

    return {"locked": True, "successor_id": str(successor_id) if successor_id else None,
            "tasks_reassigned": tasks_reassigned, "projects_reassigned": projects_reassigned,
            "reports_reassigned": reports_reassigned}


async def request_unlock(db: AsyncSession, *, email: str, device_uuid: str) -> None:
    email = email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None or user.status != UserStatus.locked:
        return  # luôn im lặng — không lộ email tồn tại
    root = (await db.execute(select(User).where(
        User.workspace_id == user.workspace_id, User.is_root,
    ))).scalar_one_or_none()
    if root:
        await notify(db, workspace_id=user.workspace_id, recipient_id=root.id,
                     type="unlock_request",
                     payload={"user_id": str(user.id), "email": email,
                              "device_uuid": device_uuid})
        await db.commit()
