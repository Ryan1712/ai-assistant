"""Directive: giao việc chính thức có state machine riêng (Phase 3 §7).

Khác update_task/assign_task ở chỗ người nhận PHẢI xác nhận đã nhận việc.
Quyền tạo tách biệt khỏi work_service (xem app/permissions.py::can_assign_directive) —
không mở rộng phạm vi quyền của assign_task/create_task/update_task hiện có.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Directive, DirectiveStatus, Role, Task, User
from app.permissions import can_assign_directive, direct_report_ids
from app.services import email_service
from app.services.notify import notify


def _directive_out(d: Directive) -> dict:
    return {
        "id": str(d.id), "created_by": str(d.created_by), "recipient_id": str(d.recipient_id),
        "task_id": str(d.task_id) if d.task_id else None,
        "verbatim_text": d.verbatim_text, "structured_summary": d.structured_summary,
        "deadline": d.deadline.isoformat() if d.deadline else None,
        "status": d.status.value, "response_text": d.response_text,
        "created_at": d.created_at.isoformat(),
    }


async def create_directive(db: AsyncSession, actor: User, *, recipient_id: uuid.UUID,
                           task_id: uuid.UUID | None = None, verbatim_text: str,
                           structured_summary: str = "",
                           deadline: datetime | None = None) -> dict:
    if not await can_assign_directive(db, actor, recipient_id):
        raise HTTPException(403, "forbidden")
    recipient = await db.get(User, recipient_id)
    if recipient is None or recipient.workspace_id != actor.workspace_id:
        raise HTTPException(404, "recipient_not_found")
    task: Task | None = None
    if task_id is not None:
        task = await db.get(Task, task_id)
        if task is None or task.workspace_id != actor.workspace_id:
            raise HTTPException(404, "task_not_found")
    directive = Directive(workspace_id=actor.workspace_id, created_by=actor.id,
                          recipient_id=recipient_id, task_id=task_id,
                          verbatim_text=verbatim_text, structured_summary=structured_summary,
                          deadline=deadline)
    db.add(directive)
    await db.flush()  # can directive.id truoc khi dua vao notify payload
    await notify(db, workspace_id=actor.workspace_id, recipient_id=recipient_id,
                type="directive_assigned",
                payload={"directive_id": str(directive.id), "from_name": actor.full_name,
                         "summary": structured_summary or verbatim_text,
                         "task_title": task.title if task else None,
                         "deadline": deadline.isoformat() if deadline else None})
    subject = f"Việc mới: {structured_summary or verbatim_text[:60]}"
    body = f"{verbatim_text}\n\n---\n{structured_summary}" if structured_summary else verbatim_text
    await email_service.send_email(db, actor, recipient_id, subject, body, task_id=task_id)
    await db.commit()
    return _directive_out(directive)


async def _get_own_directive_or_404(db: AsyncSession, actor: User,
                                    directive_id: uuid.UUID) -> Directive:
    d = await db.get(Directive, directive_id)
    if d is None or d.workspace_id != actor.workspace_id or d.recipient_id != actor.id:
        raise HTTPException(404, "directive_not_found")
    return d


_ACKABLE = {DirectiveStatus.sent, DirectiveStatus.seen, DirectiveStatus.question,
           DirectiveStatus.renegotiate}


async def ack_directive(db: AsyncSession, actor: User, directive_id: uuid.UUID) -> dict:
    d = await _get_own_directive_or_404(db, actor, directive_id)
    if d.status not in _ACKABLE:
        raise HTTPException(409, "directive_not_ackable")
    d.status = DirectiveStatus.acked
    d.acked_at = datetime.now(timezone.utc)
    await notify(db, workspace_id=d.workspace_id, recipient_id=d.created_by,
                type="directive_acked",
                payload={"directive_id": str(d.id), "recipient_name": actor.full_name})
    await db.commit()
    return _directive_out(d)


async def raise_question(db: AsyncSession, actor: User, directive_id: uuid.UUID,
                         question_text: str) -> dict:
    d = await _get_own_directive_or_404(db, actor, directive_id)
    if d.status not in _ACKABLE:
        raise HTTPException(409, "directive_not_ackable")
    d.status = DirectiveStatus.question
    d.response_text = question_text
    await notify(db, workspace_id=d.workspace_id, recipient_id=d.created_by,
                type="directive_question",
                payload={"directive_id": str(d.id), "question": question_text,
                         "from_name": actor.full_name})
    await db.commit()
    return _directive_out(d)


async def renegotiate(db: AsyncSession, actor: User, directive_id: uuid.UUID,
                      reason: str, new_deadline_proposal: datetime | None = None) -> dict:
    d = await _get_own_directive_or_404(db, actor, directive_id)
    if d.status not in _ACKABLE:
        raise HTTPException(409, "directive_not_ackable")
    d.status = DirectiveStatus.renegotiate
    d.response_text = reason
    await notify(db, workspace_id=d.workspace_id, recipient_id=d.created_by,
                type="directive_renegotiate",
                payload={"directive_id": str(d.id),
                         "proposal": new_deadline_proposal.isoformat()
                                    if new_deadline_proposal else None,
                         "reason": reason, "from_name": actor.full_name})
    await db.commit()
    return _directive_out(d)


async def get_directive_status(db: AsyncSession, actor: User) -> dict:
    if actor.role == Role.ceo:
        stmt = select(Directive).where(Directive.workspace_id == actor.workspace_id)
    elif actor.role == Role.manager:
        report_ids = await direct_report_ids(db, actor)
        stmt = select(Directive).where(
            Directive.workspace_id == actor.workspace_id,
            or_(Directive.created_by == actor.id, Directive.recipient_id == actor.id,
                Directive.recipient_id.in_(report_ids) if report_ids else False))
    else:
        stmt = select(Directive).where(Directive.workspace_id == actor.workspace_id,
                                       Directive.recipient_id == actor.id)
    rows = (await db.execute(stmt.order_by(Directive.created_at.desc()))).scalars().all()
    result = {"directives": [_directive_out(d) for d in rows]}
    if not rows:
        result["note"] = "Không có directive nào trong phạm vi bạn thấy."
    return result


async def escalate_overdue(db: AsyncSession, *, now: datetime | None = None) -> int:
    """arq cron (mỗi phút): >24h chưa ack (status sent/seen) và chưa nhắc lần nào -> nhắc
    người nhận 1 lần; >48h vẫn vậy và đã nhắc -> báo người giao 1 lần. Guard cột
    remind_count/escalated_at để cron chạy mỗi phút không spam (giống
    Task.deadline_reminder_sent_at)."""
    now = now or datetime.now(timezone.utc)
    h24_ago = now - timedelta(hours=24)
    h48_ago = now - timedelta(hours=48)
    count = 0

    to_remind = (await db.execute(select(Directive).where(
        Directive.status.in_([DirectiveStatus.sent, DirectiveStatus.seen]),
        Directive.created_at <= h24_ago, Directive.remind_count == 0,
    ))).scalars().all()
    for d in to_remind:
        await notify(db, workspace_id=d.workspace_id, recipient_id=d.recipient_id,
                    type="directive_reminder",
                    payload={"directive_id": str(d.id), "summary": d.structured_summary})
        d.remind_count = 1
        count += 1

    to_escalate = (await db.execute(select(Directive).where(
        Directive.status.in_([DirectiveStatus.sent, DirectiveStatus.seen]),
        Directive.created_at <= h48_ago, Directive.remind_count >= 1,
        Directive.escalated_at.is_(None),
    ))).scalars().all()
    for d in to_escalate:
        recipient = await db.get(User, d.recipient_id)
        await notify(db, workspace_id=d.workspace_id, recipient_id=d.created_by,
                    type="directive_escalation",
                    payload={"directive_id": str(d.id),
                             "recipient_name": recipient.full_name if recipient else "?"})
        d.escalated_at = now
        count += 1

    await db.commit()
    return count
