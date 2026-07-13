# Plan 9 — Báo cáo định kỳ tự động (funtional-plan 6.5 nâng cao, Giai đoạn 3)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Checkbox (`- [ ]`) để tracking.

**Goal:** CEO đặt lịch qua chat ("gửi báo cáo tiến độ mỗi sáng thứ 2 lúc 8h") → hệ thống tự sinh báo cáo Excel đúng lịch, không cần CEO nhắc lại. Tính năng gói **Advanced**.

**Architecture:** `ReportSchedule` (cron đơn giản: weekday tùy chọn + hour + minute + filters giống `generate_report`). 1 arq cron job (`arq.cron.cron`, chạy mỗi phút) quét lịch tới hạn, gọi lại `report_service.generate_report` sẵn có, `notify()` cho người nhận, rồi tính `next_run_at` kế tiếp. Không thêm bảng lưu trạng thái phức tạp — `next_run_at` đủ để driver.

**Tech Stack:** BE như cũ, dùng `arq.cron.cron` đã có sẵn trong `arq==0.26.*` (không thêm dependency).

## Global Constraints (CLAUDE.md)
- workspace_id mọi bảng; quyền ở service layer; actor từ JWT; TDD, mỗi task 1 commit; export openapi khi đổi contract.

## Quyết định thiết kế
- **Gói Advanced only** — dùng `plans.plan_allows(ws, "scheduled_reports")` (thêm feature key mới vào `ADVANCED_FEATURES`, pattern giống `ceo_portal`), lỗi `403 advanced_plan_required`.
- **Lịch:** `weekday` (0=Mon..6=Sun, `None` = hàng ngày) + `hour` (0-23) + `minute` (0-59), UTC — không hỗ trợ timezone khác trong bản này (chưa có yêu cầu, YAGNI).
- **Filters:** tái dùng đúng field của `generate_report` (project_id/assignee_id/status) — KHÔNG có date_from/date_to vì báo cáo định kỳ luôn là snapshot "tại thời điểm chạy", giống cách CEO tự yêu cầu "báo cáo bây giờ".
- **Người nhận:** `recipient_id` tùy chọn, mặc định = người tạo lịch (CEO). Không giới hạn phải là chính CEO — CEO có thể đặt lịch gửi cho manager.
- **Tool không sensitive** — tạo lịch không phải hành động phá hủy, không cần xác nhận 2 bước (giống `create_project`).
- **Cron chạy mỗi phút, quét DB** thay vì đăng ký 1 arq cron job/lịch — arq cron job là khai báo tĩnh lúc khởi động worker, không hợp với lịch động do CEO tạo runtime qua chat.

### Task 1: `compute_next_run` thuần + model `ReportSchedule` (TDD)
- [ ] `app/models.py`: thêm `ReportSchedule`:
  ```python
  class ReportSchedule(Base):
      __tablename__ = "report_schedules"
      id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
      workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
      created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
      recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
      weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
      hour: Mapped[int] = mapped_column(Integer)
      minute: Mapped[int] = mapped_column(Integer, default=0)
      project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
      assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
      status: Mapped[TaskStatus | None] = mapped_column(Enum(TaskStatus), nullable=True)
      active: Mapped[bool] = mapped_column(Boolean, default=True)
      last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
      next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
      created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
  ```
- [ ] `app/services/report_schedule_service.py::compute_next_run(after: datetime, weekday: int | None, hour: int, minute: int) -> datetime` — hàm thuần:
  ```python
  from datetime import datetime, timedelta

  def compute_next_run(after: datetime, weekday: int | None, hour: int, minute: int) -> datetime:
      candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
      if candidate <= after:
          candidate += timedelta(days=1)
      if weekday is not None:
          while candidate.weekday() != weekday:
              candidate += timedelta(days=1)
      return candidate
  ```
- [ ] Test `tests/test_report_schedule_service.py`: `after=2026-07-13 10:00 (thứ Hai, weekday=0)`:
  - `compute_next_run(after, None, 8, 0)` → `2026-07-14 08:00` (hôm nay 8h đã qua → mai)
  - `compute_next_run(after, None, 14, 0)` → `2026-07-13 14:00` (hôm nay 14h chưa tới)
  - `compute_next_run(after, 0, 8, 0)` → `2026-07-20 08:00` (thứ Hai tuần sau, vì thứ Hai tuần này 8h đã qua)
  - `compute_next_run(after, 2, 8, 0)` → `2026-07-15 08:00` (thứ Tư tuần này)
- [ ] Commit `feat(be): compute_next_run thuan + model ReportSchedule`.

### Task 2: `plans.py` thêm feature `scheduled_reports` (TDD)
- [ ] `app/plans.py`: thêm `"scheduled_reports"` vào `ADVANCED_FEATURES`.
- [ ] Test bổ sung vào `tests/test_subscription.py`: `plan_allows(basic_ws, "scheduled_reports") is False`; `plan_allows(advanced_ws, "scheduled_reports") is True`.
- [ ] Commit `feat(be): gate scheduled_reports theo goi Advanced`.

### Task 3: `create_schedule` / `list_schedules` / `delete_schedule` (TDD)
- [ ] `report_schedule_service.py` thêm:
  ```python
  async def create_schedule(db, actor, *, weekday, hour, minute,
                            project_id=None, assignee_id=None, status=None,
                            recipient_id=None) -> ReportSchedule:
      require_ceo(actor)
      ws = await db.get(Workspace, actor.workspace_id)
      if not plans.plan_allows(ws, "scheduled_reports"):
          raise HTTPException(403, "advanced_plan_required")
      if project_id is not None:
          project = await db.get(Project, project_id)
          if project is None or project.workspace_id != actor.workspace_id:
              raise HTTPException(404, "project_not_found")
      recipient = actor.id
      if recipient_id is not None:
          target = await db.get(User, recipient_id)
          if target is None or target.workspace_id != actor.workspace_id:
              raise HTTPException(404, "user_not_found")
          recipient = recipient_id
      now = datetime.now(timezone.utc)
      sched = ReportSchedule(workspace_id=actor.workspace_id, created_by=actor.id,
                             recipient_id=recipient, weekday=weekday, hour=hour,
                             minute=minute, project_id=project_id, assignee_id=assignee_id,
                             status=status, next_run_at=compute_next_run(now, weekday, hour, minute))
      db.add(sched)
      await db.commit()
      return sched

  async def list_schedules(db, actor) -> list[ReportSchedule]:
      require_ceo(actor)
      rows = await db.execute(select(ReportSchedule).where(
          ReportSchedule.workspace_id == actor.workspace_id).order_by(ReportSchedule.created_at.asc()))
      return list(rows.scalars())

  async def delete_schedule(db, actor, schedule_id) -> None:
      require_ceo(actor)
      sched = await db.get(ReportSchedule, schedule_id)
      if sched is None or sched.workspace_id != actor.workspace_id:
          raise HTTPException(404, "schedule_not_found")
      await db.delete(sched)
      await db.commit()
  ```
- [ ] Test: CEO tạo lịch weekday=0 hour=8 → `next_run_at` đúng bằng `compute_next_run`; employee tạo → 403 `forbidden` (từ `require_ceo`); workspace Basic tạo → 403 `advanced_plan_required`; project_id sai workspace → 404; list chỉ trả lịch đúng workspace; delete lịch của workspace khác → 404; delete đúng → biến mất khỏi list.
- [ ] Commit `feat(be): report_schedule_service create/list/delete`.

### Task 4: `run_due_schedules` — lõi cron (TDD)
- [ ] `report_schedule_service.py` thêm:
  ```python
  async def run_due_schedules(db: AsyncSession, *, now: datetime | None = None) -> list[dict]:
      now = now or datetime.now(timezone.utc)
      due = (await db.execute(select(ReportSchedule).where(
          ReportSchedule.active.is_(True), ReportSchedule.next_run_at <= now
      ))).scalars().all()
      results = []
      for sched in due:
          actor = await db.get(User, sched.created_by)
          if actor is None:
              continue
          out = await report_service.generate_report(
              db, actor, project_id=sched.project_id, assignee_id=sched.assignee_id,
              status=sched.status)
          await notify(db, workspace_id=sched.workspace_id, recipient_id=sched.recipient_id,
                      type="scheduled_report",
                      payload={"report_id": out["report_id"], "summary": out["summary"],
                               "schedule_id": str(sched.id)})
          sched.last_run_at = now
          sched.next_run_at = compute_next_run(now, sched.weekday, sched.hour, sched.minute)
          results.append({"schedule_id": str(sched.id), "report_id": out["report_id"]})
      await db.commit()
      return results
  ```
- [ ] Test: lịch `next_run_at` trong quá khứ → sau khi chạy: có `Report` mới trong DB, có `Notification` cho `recipient_id`, `last_run_at` = `now` truyền vào, `next_run_at` đẩy sang lần kế tiếp đúng theo `compute_next_run`. Lịch `next_run_at` trong tương lai → không chạy, không tạo Report. Lịch `active=False` → không chạy dù tới hạn. 2 lịch tới hạn trong 2 workspace khác nhau → cả 2 đều chạy, mỗi report đúng workspace.
- [ ] Commit `feat(be): run_due_schedules - loi cron sinh bao cao dinh ky`.

### Task 5: Đăng ký cron job trong worker (TDD)
- [ ] `app/agent/worker.py`: import `from arq.cron import cron`; thêm hàm:
  ```python
  async def check_report_schedules(ctx: dict) -> None:
      async with ctx["session_factory"]() as db:
          await report_schedule_service.run_due_schedules(db)
  ```
  `WorkerSettings.cron_jobs = [cron(check_report_schedules, second=0)]` (chạy đầu mỗi phút).
- [ ] Test bổ sung `tests/test_worker.py`: `WorkerSettings.cron_jobs` không rỗng; tên job đúng `check_report_schedules` (so `job.coroutine.__name__` hoặc tương đương công khai của `CronJob`).
- [ ] Commit `feat(be): dang ky cron job check_report_schedules moi phut`.

### Task 6: Tool chat + REST + migration + openapi
- [ ] `app/agent/tools.py`: 3 tool `create_report_schedule` (weekday tùy chọn, hour, minute, filters, recipient_id tùy chọn — mô tả rõ: "Tự tính weekday từ ngôn ngữ tự nhiên, VD 'mỗi thứ 2' → weekday=0. Chỉ CEO, cần gói Advanced."), `list_report_schedules`, `delete_report_schedule`. Không sensitive.
- [ ] `app/schemas.py`: `ReportScheduleCreateIn`, `ReportScheduleOut` (id, weekday, hour, minute, project_id, assignee_id, status, recipient_id, active, last_run_at, next_run_at).
- [ ] `app/api/report_schedules.py`: `POST /api/v1/report-schedules`, `GET /api/v1/report-schedules`, `DELETE /api/v1/report-schedules/{id}` (204). Đăng ký router trong `main.py`.
- [ ] Test: 3 tool qua `call_tool`; REST 3 endpoint qua httpx test client (tạo/list/xóa, 403 khi Basic, 403 khi employee).
- [ ] Migration tay bảng `report_schedules`. Full pytest. `python scripts/export_openapi.py`.
- [ ] Commit `feat(be): tool + REST bao cao dinh ky + migration + openapi`.

## Ghi chú
- Không làm FE cho tính năng này trong plan này — chat tool đã đủ dùng ngay (CEO nói "gửi báo cáo mỗi thứ 2" là xong); FE UI liệt kê/xóa lịch có thể thêm sau nếu cần, dùng luôn 3 REST endpoint đã có.
- Múi giờ: mọi giờ trong `hour`/`minute` là UTC. Nếu sau này cần theo giờ VN (UTC+7), CEO tự trừ 7 giờ khi nói với AI hoặc bổ sung field timezone sau — chưa có yêu cầu rõ ràng nên YAGNI.
