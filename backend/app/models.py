import enum
import uuid
from datetime import datetime, timedelta, timezone

from datetime import date

from sqlalchemy import String, Boolean, ForeignKey, DateTime, Date, Enum, JSON, Uuid, Integer, Text, UniqueConstraint, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    ceo = "ceo"
    manager = "manager"
    employee = "employee"


class UserStatus(str, enum.Enum):
    active = "active"
    locked = "locked"
    # Tao truoc boi CEO (create_employee), chua tu kich hoat/dat mat khau - login
    # thuong bi chan (giong locked) toi khi activate_account() thanh cong.
    pending = "pending"


class WorkspacePlan(str, enum.Enum):
    basic = "basic"
    advanced = "advanced"


def _invite_code() -> str:
    import secrets
    import string
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    plan: Mapped[WorkspacePlan] = mapped_column(Enum(WorkspacePlan),
                                                default=WorkspacePlan.basic)
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, index=True,
                                             default=_invite_code)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_root: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.active)
    # {} = mọi loại thông báo bật mặc định; key set False = user tự tắt loại đó
    # (funtional-plan 6.6: "người dùng có thể tắt bớt loại thông báo nếu quá nhiều").
    notification_prefs: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    device_uuid: Mapped[str] = mapped_column(String(64))
    device_name: Mapped[str] = mapped_column(String(255), default="")
    push_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LoginEvent(Base):
    __tablename__ = "login_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    device_uuid: Mapped[str] = mapped_column(String(64))
    device_name: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AccountEvent(Base):
    __tablename__ = "account_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    target_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[Role] = mapped_column(Enum(Role))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # None = invite kieu cu (khong con duong tao moi, giu de tuong thich du lieu cu neu co).
    # Co gia tri = "ma kich hoat" cho User da duoc CEO tao truoc qua create_employee - token
    # nay chi dung de KICH HOAT (dat mat khau), khong tu dang ky thong tin moi.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"


class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    goal: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.todo)
    percent: Mapped[int] = mapped_column(Integer, default=0)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Đánh dấu đã nhắc "sắp tới hạn" 1 lần (funtional-plan 6.6) — tránh spam mỗi phút
    # cron chạy; reset về None nếu deadline dời sang thời điểm khác (xem update_task).
    deadline_reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    priority: Mapped[TaskPriority] = mapped_column(Enum(TaskPriority), default=TaskPriority.medium)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TaskAssignee(Base):
    __tablename__ = "task_assignees"
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_task_assignee"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DirectiveStatus(str, enum.Enum):
    sent = "sent"
    seen = "seen"
    acked = "acked"
    question = "question"
    renegotiate = "renegotiate"
    done = "done"
    cancelled = "cancelled"


class Directive(Base):
    """Giao việc chính thức có state machine riêng (Phase 3 §7.1) — khác
    update_task/assign_task ở chỗ người nhận PHẢI xác nhận đã nhận việc."""
    __tablename__ = "directives"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    verbatim_text: Mapped[str] = mapped_column(Text)
    structured_summary: Mapped[str] = mapped_column(Text, default="")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[DirectiveStatus] = mapped_column(Enum(DirectiveStatus),
                                                    default=DirectiveStatus.sent)
    # Cau hoi (question) hoac ly do de nghi doi han (renegotiate) cua nguoi nhan.
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Guard chong spam cho escalate_overdue (cron moi phut) - cung pattern
    # deadline_reminder_sent_at cua Task.
    remind_count: Mapped[int] = mapped_column(Integer, default=0)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TaskUpdate(Base):
    __tablename__ = "task_updates"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text, default="")
    percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[TaskStatus | None] = mapped_column(Enum(TaskStatus), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TaskComment(Base):
    __tablename__ = "task_comments"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SkillKind(str, enum.Enum):
    profile = "profile"
    knowledge = "knowledge"


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[SkillKind] = mapped_column(Enum(SkillKind))
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SkillVersion(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("skill_id", "version", name="uq_skill_version"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SkillGrant(Base):
    __tablename__ = "skill_grants"
    __table_args__ = (UniqueConstraint("skill_id", "user_id", name="uq_skill_grant"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    granted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SkillUsageLog(Base):
    __tablename__ = "skill_usage_log"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


def _today() -> date:
    # Thi truong chinh la VN (UTC+7) — mac dinh note_date khi khong truyen tuong
    # minh (vd tool chat create_note) phai theo ngay lich VN, khong phai UTC.
    return (datetime.now(timezone.utc) + timedelta(hours=7)).date()


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    note_date: Mapped[date] = mapped_column(Date, default=_today, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Instruction(Base):
    __tablename__ = "instructions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class InstructionVersion(Base):
    __tablename__ = "instruction_versions"
    __table_args__ = (UniqueConstraint("instruction_id", "version", name="uq_instruction_version"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    instruction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instructions.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ChatRequestStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    awaiting_confirmation = "awaiting_confirmation"
    # Đường sâu (Phase 4 §8.2): đã ghi ack Message + enqueue job phân tích chạy nền
    # bằng model_smart, CHƯA xong thật — job sẽ tự chuyển sang done khi hoàn tất.
    deep_running = "deep_running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 5.7: mất mạng/đóng app → hold queue; chỉ "tiếp tục công việc" mới clear
    queue_held: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Phase 5 (session model): nén hội thoại cũ + xoay conversation ngầm.
    # rolling_summary tiêm vào SYSTEM prompt (KHÔNG thành message). summary_through_at
    # = mốc message đã gộp vào summary (message sau mốc gửi nguyên văn). archived_at
    # != None = conversation đã bị xoay ra khỏi luồng sống.
    rolling_summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    summary_through_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ChatRequest(Base):
    __tablename__ = "chat_requests"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[ChatRequestStatus] = mapped_column(Enum(ChatRequestStatus),
                                                       default=ChatRequestStatus.queued)
    queue_position: Mapped[float] = mapped_column(Float)
    # Đính kèm ghi âm làm input cho AI (spec 2026-07-19): file dài user ném vào
    # chat; transcript (khi có STT) được worker append vào Message.content.
    voice_note_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("voice_notes.id", ondelete="SET NULL"), nullable=True)
    pending_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    chat_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chat_requests.id"),
                                                               nullable=True)
    voice_note_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("voice_notes.id", ondelete="SET NULL"), nullable=True)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole))
    content: Mapped[list] = mapped_column(JSON)
    # Phase 4 §8.2: ack message của run_deep_ack_turn — hiển thị cho user bình
    # thường nhưng KHÔNG BAO GIỜ đưa vào lịch sử gửi lại cho model (xem
    # _load_history/loop.py) — nó chỉ là câu xác nhận UI, không phải suy luận
    # thật, và đứng giữa user-text gốc + tool_use lượt sau của CHÍNH request đó
    # sẽ phá quy tắc user/assistant xen kẽ bắt buộc của Anthropic.
    is_ack: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UsageLog(Base):
    __tablename__ = "usage_log"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    chat_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chat_requests.id"),
                                                               nullable=True)
    # Hardening truoc Phase 3 (khong bang/service moi — chi mo rong field du de tra
    # loi "feature/user nao ton tien"): user_id = actor thuc hien; feature = nguon
    # goi (mac dinh "chat", Phase 3+ them "directive"/"deep_analysis"...); status =
    # nguyen van stop_reason cua LUOT GOI NAY (khong phai trang thai ca ChatRequest —
    # cai do da co o ChatRequest.status/.error, khong lap lai); estimated_cost la uoc
    # luong noi bo (KHONG dung tinh hoa don that).
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    feature: Mapped[str] = mapped_column(String(32), default="chat")
    status: Mapped[str] = mapped_column(String(32), default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class VoiceNote(Base):
    __tablename__ = "voice_notes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(512))
    transcript: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(16), default="und")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    # pending = chưa có STT thật; queued/processing/done/failed khi transcribe async chạy
    transcript_status: Mapped[str] = mapped_column(String(16), default="pending",
                                                    server_default="pending")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    file_path: Mapped[str] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EmailMessage(Base):
    __tablename__ = "email_messages"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32), default="task_summary")
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    file_path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ReportSchedule(Base):
    __tablename__ = "report_schedules"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0=Mon..6=Sun, None=daily
    hour: Mapped[int] = mapped_column(Integer)
    minute: Mapped[int] = mapped_column(Integer, default=0)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[TaskStatus | None] = mapped_column(Enum(TaskStatus), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Embedding(Base):
    """Index ngữ nghĩa (Phase 6 §10.3) — nguồn: note | task_update | comment |
    chat_message (mở rộng thêm loại sau chỉ cần thêm string, không đổi bảng).

    embedding lưu JSON list[float] thay vì kiểu Vector của pgvector — test
    suite chạy SQLite in-memory (xem tests/conftest.py), không có extension
    Postgres; so khớp bằng cosine similarity thuần Python (app/services/
    embedding_service.py), cùng lý do fuzzy_match.py chọn Jaccard-trigram
    thay vì pg_trgm.

    Nguồn (note/task_update/comment/chat_message) đều bất biến sau khi tạo
    (không có PATCH) nên không cần re-embed; quyền xem KHÔNG kiểm ở bảng này
    — semantic_search() luôn join ngược bảng gốc + permissions.py tại thời
    điểm truy vấn."""
    __tablename__ = "embeddings"
    __table_args__ = (UniqueConstraint("source_type", "source_id", "chunk_no",
                                       name="uq_embedding_source_chunk"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    chunk_no: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WorkspaceMemory(Base):
    """Fact bền do distiller (cron đêm, app/services/distiller_service.py) chưng
    cất từ hoạt động công ty trong ngày, hoặc CEO tự thêm sau này (Phase 6 §10.2).

    scope: "workspace" (mọi actor trong công ty đều nạp) | "user:<uuid>" (chỉ
    actor đó — CHƯA dùng ở v1, distiller hiện chỉ sinh scope="workspace" để
    tránh rủi ro rò rỉ nội dung chat riêng tư của 1 user vào bộ nhớ chung — xem
    docstring distiller_service.py). archived_at != None = đã "quên" (soft
    delete qua tool forget_memory, CEO-only)."""
    __tablename__ = "workspace_memories"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    scope: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))  # "distiller" | "user_explicit"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentTrace(Base):
    """Trace 1 LẦN CHẠY agent loop của 1 chat_request (Phase 0, spec AI upgrade 4.1).

    1 request có thể có nhiều dòng: sau khi user confirm sensitive tool, request
    quay về queued và loop chạy lần nữa. Debug đọc qua GET /api/v1/admin/traces/…
    """
    __tablename__ = "agent_traces"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    chat_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_requests.id"),
                                                        index=True)
    route: Mapped[str] = mapped_column(String(16), default="fast")
    # fast | deep (Phase 4) | confirm (tool chạy trong resolve_confirmation, không qua model)
    model: Mapped[str] = mapped_column(String(64), default="")
    iterations: Mapped[int] = mapped_column(Integer, default=0)
    # ghi NGUYÊN VĂN stop_reason (debug trung thực); thường gặp: cancelled | max_iterations |
    # end_turn | max_tokens | awaiting_confirmation | error
    stop_reason: Mapped[str] = mapped_column(String(32), default="")
    # [{name, latency_ms, input, output}] — input/output là JSON string cắt 500 ký tự
    tools_called: Mapped[list] = mapped_column(JSON, default=list)
    total_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
