"""Nhật ký thay đổi (funtional-plan §8, §4.4) — query-time merge 5 nguồn, CEO-only.

3/4 nguồn đã có sẵn dữ liệu (TaskUpdate, LoginEvent, InstructionVersion, SkillVersion) —
chỉ AccountEvent là bảng mới (lịch sử khóa/mở/nghỉ việc/đổi vai trò). Không lưu trùng
lặp dữ liệu — mỗi lần gọi query lại 5 bảng, gộp + sort trong Python, không có bảng
audit trung gian.
"""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AccountEvent, InstructionVersion, LoginEvent, SkillVersion, TaskUpdate, User,
)
from app.permissions import require_ceo


def _bounds(created_at_col, date_from: date | None, date_to: date | None) -> list:
    conds = []
    if date_from is not None:
        conds.append(created_at_col >= date_from)
    if date_to is not None:
        conds.append(created_at_col < date_to + timedelta(days=1))
    return conds


async def list_audit_events(db: AsyncSession, actor: User, *,
                            date_from: date | None = None,
                            date_to: date | None = None) -> list[dict]:
    require_ceo(actor)
    events: list[dict] = []

    rows = (await db.execute(
        select(TaskUpdate).where(TaskUpdate.workspace_id == actor.workspace_id,
                                 *_bounds(TaskUpdate.created_at, date_from, date_to))
        .order_by(TaskUpdate.created_at.desc()).limit(200))).scalars()
    for r in rows:
        events.append({
            "type": "task_update", "actor_id": r.author_id,
            "summary": f"Cập nhật task — {r.percent}%" + (f", {r.status.value}" if r.status else ""),
            "created_at": r.created_at,
        })

    rows = (await db.execute(
        select(LoginEvent).where(LoginEvent.workspace_id == actor.workspace_id,
                                 *_bounds(LoginEvent.created_at, date_from, date_to))
        .order_by(LoginEvent.created_at.desc()).limit(200))).scalars()
    for r in rows:
        events.append({
            "type": "login", "actor_id": r.user_id,
            "summary": f"Đăng nhập — {r.device_name or r.device_uuid}",
            "created_at": r.created_at,
        })

    rows = (await db.execute(
        select(InstructionVersion).where(InstructionVersion.workspace_id == actor.workspace_id,
                                         *_bounds(InstructionVersion.created_at, date_from, date_to))
        .order_by(InstructionVersion.created_at.desc()).limit(200))).scalars()
    for r in rows:
        events.append({
            "type": "instruction_edit", "actor_id": r.created_by,
            "summary": f"Sửa instruction — phiên bản {r.version}",
            "created_at": r.created_at,
        })

    rows = (await db.execute(
        select(SkillVersion).where(SkillVersion.workspace_id == actor.workspace_id,
                                   *_bounds(SkillVersion.created_at, date_from, date_to))
        .order_by(SkillVersion.created_at.desc()).limit(200))).scalars()
    for r in rows:
        events.append({
            "type": "skill_edit", "actor_id": r.created_by,
            "summary": f"Sửa skill — phiên bản {r.version}",
            "created_at": r.created_at,
        })

    rows = (await db.execute(
        select(AccountEvent).where(AccountEvent.workspace_id == actor.workspace_id,
                                   *_bounds(AccountEvent.created_at, date_from, date_to))
        .order_by(AccountEvent.created_at.desc()).limit(200))).scalars()
    for r in rows:
        events.append({
            "type": "account_event", "actor_id": r.actor_id, "target_user_id": r.target_user_id,
            "summary": r.detail, "created_at": r.created_at,
        })

    events.sort(key=lambda e: e["created_at"], reverse=True)
    events = events[:200]

    actor_ids = {e["actor_id"] for e in events} | {
        e["target_user_id"] for e in events if "target_user_id" in e}
    names = {}
    if actor_ids:
        rows = (await db.execute(select(User).where(
            User.id.in_(actor_ids), User.workspace_id == actor.workspace_id))).scalars()
        names = {u.id: u.full_name for u in rows}

    for e in events:
        e["actor_name"] = names.get(e["actor_id"], "?")
        e["actor_id"] = str(e["actor_id"])
        if "target_user_id" in e:
            e["target_name"] = names.get(e["target_user_id"], "?")
            e["target_user_id"] = str(e["target_user_id"])

    return events
