"""Email theo vai trò (funtional-plan 6.4) — ma trận tương tác: employee ⇎ employee,
mọi cặp khác trong cùng workspace được phép.

EmailClient real CHƯA implement — chờ product chốt OAuth send-as hay SMTP
(phụ lục funtional-plan). Mặc định MockEmailClient (email_mock=True): mail vẫn
được ghi vào email_messages làm nguồn chuẩn trong app.
"""
import uuid
from typing import Protocol

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import EmailMessage, Role, User
from app.permissions import get_visible_task_or_404, visible_project_ids
from app.services.notify import notify


class EmailClient(Protocol):
    async def send(self, *, from_email: str, to_email: str, subject: str,
                   body: str) -> None: ...


class MockEmailClient:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, *, from_email: str, to_email: str, subject: str,
                   body: str) -> None:
        self.sent.append({"from": from_email, "to": to_email, "subject": subject,
                          "body": body})


mock_email_client = MockEmailClient()


def get_email_client() -> EmailClient:
    if get_settings().email_mock:
        return mock_email_client
    raise NotImplementedError(
        "Email client thật chưa được chọn (OAuth send-as vs SMTP) — xem phụ lục funtional-plan")


def _check_matrix(sender: User, recipient: User) -> None:
    if sender.role == Role.employee and recipient.role == Role.employee:
        raise HTTPException(403, "interaction_not_allowed")


async def send_email(db: AsyncSession, actor: User, recipient_id: uuid.UUID,
                     subject: str, body: str, task_id: uuid.UUID | None = None,
                     project_id: uuid.UUID | None = None) -> EmailMessage:
    recipient = await db.get(User, recipient_id)
    if recipient is None or recipient.workspace_id != actor.workspace_id:
        raise HTTPException(404, "recipient_not_found")
    _check_matrix(actor, recipient)
    if task_id is not None:
        await get_visible_task_or_404(db, actor, task_id)
    if project_id is not None and project_id not in await visible_project_ids(db, actor):
        raise HTTPException(404, "project_not_found")
    email = EmailMessage(workspace_id=actor.workspace_id, sender_id=actor.id,
                         recipient_id=recipient.id, subject=subject, body=body,
                         task_id=task_id, project_id=project_id)
    db.add(email)
    await get_email_client().send(from_email=actor.email, to_email=recipient.email,
                                  subject=subject, body=body)
    await notify(db, workspace_id=actor.workspace_id, recipient_id=recipient.id,
                type="email_received",
                payload={"from_user": str(actor.id), "from_name": actor.full_name,
                         "subject": subject})
    await db.commit()
    return email


async def list_emails(db: AsyncSession, actor: User, box: str = "inbox") -> list[dict]:
    field = EmailMessage.recipient_id if box == "inbox" else EmailMessage.sender_id
    rows = await db.execute(
        select(EmailMessage, User.full_name, User.email)
        .join(User, User.id == (EmailMessage.sender_id if box == "inbox"
                                else EmailMessage.recipient_id))
        .where(EmailMessage.workspace_id == actor.workspace_id, field == actor.id)
        .order_by(EmailMessage.created_at.desc())
    )
    return [{"id": str(m.id), "subject": m.subject, "body": m.body,
             "counterpart_name": name, "counterpart_email": email,
             "task_id": str(m.task_id) if m.task_id else None,
             "project_id": str(m.project_id) if m.project_id else None,
             "created_at": m.created_at}
            for m, name, email in rows.all()]
