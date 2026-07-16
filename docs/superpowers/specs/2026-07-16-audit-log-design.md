# Thiết kế — Nhật ký thay đổi (audit log)

**Ngày:** 2026-07-16 · **Trạng thái:** Đã duyệt qua brainstorming · **Spec chức năng:** [funtional-plan.md](../../../funtional-plan.md) §8 ("Nhật ký thay đổi") + §4.4 ("Có nhật ký: ai đổi gì, khi nào")

Lấp mục "Nhật ký thay đổi" của khoảng trống §8. Khảo sát trước brainstorming cho thấy 3/4 nguồn dữ liệu đã có sẵn (`TaskUpdate`, `LoginEvent`, `InstructionVersion`/`SkillVersion`) — chỉ thiếu lịch sử khóa/mở tài khoản. Đây chủ yếu là 1 tính năng **đọc/gộp** (query-time merge), không phải 1 hệ thống ghi log mới toàn bộ.

---

## 1. Phạm vi & Ranh giới

**Trong phạm vi:**
- 1 timeline hợp nhất (không tách 4 endpoint riêng) gộp 5 nguồn: `TaskUpdate` (cập nhật task), `LoginEvent` (đăng nhập), `InstructionVersion` (sửa instruction), `SkillVersion` (sửa skill), `AccountEvent` (model mới — khóa/mở/nghỉ việc/đổi vai trò).
- Model mới `AccountEvent` — bù đắp phần duy nhất chưa có dữ liệu: lịch sử khóa/mở tài khoản (§9 "Mọi lần khóa/mở khóa vào nhật ký").
- **Gộp thêm** `offboard_user`/`change_role` vào `AccountEvent` (ngoài §8 gốc chỉ nói khóa/mở, nhưng cùng bản chất — thay đổi trạng thái nhân sự CEO cần theo dõi — quyết định brainstorming, tránh làm lại gần tương tự sau này).
- Lọc theo khoảng thời gian (`date_from`/`date_to`) — quyết định brainstorming, KHÔNG lọc theo loại sự kiện hay theo người trong lần này (YAGNI, thêm sau nếu cần).
- REST 1 endpoint (`app/api/audit.py`, router mới) + 1 tool chat read-only `list_audit_events`.
- Giới hạn 200 dòng gần nhất mỗi lần gọi (tránh trả về không giới hạn).
- Quyền: **CEO-only** (`require_ceo`), theo đúng tiền lệ mọi list CEO-only khác (`list_instructions`, `list_report_schedules`...).

**Ngoài phạm vi (cố ý, YAGNI):**
- Không lọc theo loại sự kiện hay theo người (actor) — quyết định brainstorming, chỉ lọc theo ngày.
- Không phân trang (pagination) kiểu cursor/offset — 200 dòng gần nhất là đủ cho MVP, thêm sau nếu CEO cần xem sâu hơn.
- Không validate `date_from > date_to` — trả list rỗng nếu khoảng không hợp lệ/không giao nhau, giống cách các filter ngày khác trong dự án không validate chiều.
- Không có tool để CEO *xóa* hoặc *sửa* nhật ký — nhật ký là append-only, đọc-only qua tool/REST.
- **FE** — không nằm trong plan này, sẽ là 1 spec+plan riêng sau (giống tiền lệ attachment).

---

## 2. Model mới — `AccountEvent`

Thêm vào `backend/app/models.py`, đặt cạnh `LoginEvent`:

```python
class AccountEvent(Base):
    __tablename__ = "account_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    target_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(32))  # locked/unlocked/offboarded/role_changed
    detail: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

`event_type` dùng `String(32)` thay vì `Enum` — **học từ bugfix `12cce73`** (ghi trong CLAUDE.md): cột Enum autogenerate dễ vỡ migration nếu tái dùng type Postgres có sẵn. Chỉ 4 giá trị cố định, không cần ràng buộc DB-level; giống cách `Project.status` cũng dùng `String(32)` thay vì Enum trong model hiện có.

Migration mới: `alembic revision --autogenerate -m "account events table"` rồi `alembic upgrade head` — xác nhận không sinh Enum type nào.

---

## 3. Write-hook trong `auth_service.py` (4 chỗ, mỗi chỗ 2-3 dòng)

Không viết logic quyền mới — 4 hàm này đã có `require_ceo`/`_check_lock_permission`/`_check_role_change_permission` sẵn. Chỉ thêm `db.add(AccountEvent(...))` trước mỗi `commit`.

**`lock_user`** (hiện tại dòng 247-260 trong `backend/app/services/auth_service.py`) — thêm trước `await db.commit()`:
```python
    db.add(AccountEvent(workspace_id=target.workspace_id, target_user_id=target.id,
                        actor_id=actor.id, event_type="locked", detail="Khóa tài khoản"))
```

**`unlock_user`** (dòng 263-269) — thêm trước `await db.commit()`:
```python
    db.add(AccountEvent(workspace_id=target.workspace_id, target_user_id=target.id,
                        actor_id=actor.id, event_type="unlocked", detail="Mở khóa tài khoản"))
```

**`offboard_user`** (dòng 272-321) — hàm này gọi `lock_user` ngay dòng đầu (đã tự ghi `AccountEvent(event_type="locked")` + tự commit qua hook ở trên — **đây là chủ đích, không phải trùng lặp lỗi**: offboard thật sự CÓ khóa tài khoản như 1 phần hành vi của nó, nên cả 2 sự kiện "locked" và "offboarded" đều thật). Thêm ngay sau dòng `await lock_user(db, actor, target_id)`, TRƯỚC khối `if successor_id is not None:` (vì nhánh `successor_id is None` không có commit nào khác sau đó):
```python
    await lock_user(db, actor, target_id)
    db.add(AccountEvent(workspace_id=actor.workspace_id, target_user_id=target_id,
                        actor_id=actor.id, event_type="offboarded", detail="Nghỉ việc"))
    await db.commit()

    tasks_reassigned = 0
    ...
```

**`change_role`** (dòng 333-415) — cần `old_role` TRƯỚC khi `target.role` bị gán lại ở dòng 397-398, nên capture ngay sau khi load `target` (dòng 340-342):
```python
    target = await db.get(User, target_id)
    if target is None or target.workspace_id != actor.workspace_id:
        raise HTTPException(404, "user_not_found")
    old_role = target.role
```
Rồi thêm trước `await db.commit()` (dòng 409), sau khối `notify(...)` `role_changed`:
```python
    detail_parts = []
    if new_role is not None:
        detail_parts.append(f"role: {old_role.value} -> {target.role.value}")
    if new_manager_id is not None:
        detail_parts.append(f"manager_id: {new_manager_id}")
    db.add(AccountEvent(workspace_id=actor.workspace_id, target_user_id=target_id,
                        actor_id=actor.id, event_type="role_changed",
                        detail="; ".join(detail_parts) or "cap nhat quan ly"))
```
`event_type="role_changed"` bắn cả khi chỉ đổi `manager_id` (không đổi `role`) — nhất quán với `notify(type="role_changed")` đã có sẵn ngay phía trên (quyết định đã chốt ở plan role-manager-change trước: giữ 1 type chung, không tách riêng).

---

## 4. Service gộp — `backend/app/services/audit_service.py` (file mới)

```python
async def list_audit_events(db: AsyncSession, actor: User, *,
                            date_from: date | None = None,
                            date_to: date | None = None) -> list[dict]:
    require_ceo(actor)

    def _range(col):
        conds = [col.workspace_id == actor.workspace_id] if hasattr(col, "workspace_id") else []
        return conds

    events: list[dict] = []

    def _bounds(created_at_col):
        conds = []
        if date_from is not None:
            conds.append(created_at_col >= date_from)
        if date_to is not None:
            conds.append(created_at_col <= date_to)
        return conds

    rows = (await db.execute(
        select(TaskUpdate).where(TaskUpdate.workspace_id == actor.workspace_id,
                                 *_bounds(TaskUpdate.created_at))
        .order_by(TaskUpdate.created_at.desc()).limit(200))).scalars()
    for r in rows:
        events.append({"type": "task_update", "actor_id": r.author_id,
                       "summary": f"Cập nhật task — {r.percent}%" + (f", {r.status}" if r.status else ""),
                       "created_at": r.created_at})

    rows = (await db.execute(
        select(LoginEvent).where(LoginEvent.workspace_id == actor.workspace_id,
                                 *_bounds(LoginEvent.created_at))
        .order_by(LoginEvent.created_at.desc()).limit(200))).scalars()
    for r in rows:
        events.append({"type": "login", "actor_id": r.user_id,
                       "summary": f"Đăng nhập — {r.device_name or r.device_uuid}",
                       "created_at": r.created_at})

    rows = (await db.execute(
        select(InstructionVersion).where(InstructionVersion.workspace_id == actor.workspace_id,
                                         *_bounds(InstructionVersion.created_at))
        .order_by(InstructionVersion.created_at.desc()).limit(200))).scalars()
    for r in rows:
        events.append({"type": "instruction_edit", "actor_id": r.created_by,
                       "summary": f"Sửa instruction — phiên bản {r.version}",
                       "created_at": r.created_at})

    rows = (await db.execute(
        select(SkillVersion).where(SkillVersion.workspace_id == actor.workspace_id,
                                   *_bounds(SkillVersion.created_at))
        .order_by(SkillVersion.created_at.desc()).limit(200))).scalars()
    for r in rows:
        events.append({"type": "skill_edit", "actor_id": r.created_by,
                       "summary": f"Sửa skill — phiên bản {r.version}",
                       "created_at": r.created_at})

    rows = (await db.execute(
        select(AccountEvent).where(AccountEvent.workspace_id == actor.workspace_id,
                                   *_bounds(AccountEvent.created_at))
        .order_by(AccountEvent.created_at.desc()).limit(200))).scalars()
    for r in rows:
        events.append({"type": "account_event", "actor_id": r.actor_id,
                       "target_user_id": str(r.target_user_id),
                       "summary": r.detail, "created_at": r.created_at})

    events.sort(key=lambda e: e["created_at"], reverse=True)
    events = events[:200]

    actor_ids = {e["actor_id"] for e in events} | {
        e["target_user_id"] for e in events if "target_user_id" in e}
    users = (await db.execute(select(User).where(User.id.in_(actor_ids)))).scalars()
    names = {u.id: u.full_name for u in users}

    for e in events:
        e["actor_id"] = str(e["actor_id"])
        e["actor_name"] = names.get(uuid.UUID(e["actor_id"]), "?")
        if "target_user_id" in e:
            e["target_name"] = names.get(uuid.UUID(e["target_user_id"]), "?")

    return events
```

Ghi chú thiết kế:
- **Mỗi bảng nguồn giới hạn `limit(200)` TRƯỚC khi gộp** — tránh kéo về không giới hạn 1 bảng lớn (vd `TaskUpdate` có thể rất nhiều dòng nếu không có `date_from`/`date_to`). Sau gộp 5 nguồn (tối đa 1000 dòng ứng viên) mới sort + cắt còn 200 dòng cuối cùng.
- **`_bounds` dùng `date` so với cột `DateTime`** — SQLAlchemy/Postgres tự so sánh `date` với `timestamptz` được (coi `date` như đầu ngày UTC); không cần ép kiểu thủ công, giống cách các filter `on_date` khác trong dự án (`voice_service.list_voice_notes`) đang làm với so sánh Python-side chứ không phải SQL — **khác biệt cần lưu ý khi implement**: filter ngày ở đây làm ở **SQL level** (khác `list_voice_notes` lọc Python-side), nên cần test kỹ biên ngày.
- **1 query `User` gộp** để resolve `actor_name`/`target_name`, tránh N+1.
- Response cuối cùng: `list[{"type": str, "actor_id": str, "actor_name": str, "summary": str, "created_at": datetime, "target_user_id"?: str, "target_name"?: str}]` — 2 field `target_*` chỉ có ở `type="account_event"`.

---

## 5. REST endpoint

`backend/app/api/audit.py` (router mới, đăng ký trong `app/main.py` cạnh các router khác):

```python
router = APIRouter(prefix="/api/v1", tags=["audit"])

@router.get("/audit-events")
async def list_audit_events(date_from: date | None = None, date_to: date | None = None,
                            actor: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    return await audit_service.list_audit_events(db, actor, date_from=date_from, date_to=date_to)
```

---

## 6. Tool chat

`backend/app/agent/tools.py`, đặt cạnh `list_report_schedules`:

```python
class ListAuditEventsToolIn(BaseModel):
    date_from: date | None = None
    date_to: date | None = None


async def _list_audit_events(db, actor, body: ListAuditEventsToolIn) -> dict:
    events = await audit_service.list_audit_events(db, actor, date_from=body.date_from,
                                                   date_to=body.date_to)
    return {"events": events}


_register("list_audit_events", "Xem nhật ký thay đổi công ty: cập nhật task, đăng nhập, "
          "khóa/mở/nghỉ việc/đổi vai trò tài khoản, sửa instruction/skill (chỉ CEO, tối đa 200 "
          "dòng gần nhất).", ListAuditEventsToolIn, _list_audit_events)
```

Không `sensitive` — chỉ đọc, không phải hành động nhạy cảm.

---

## 7. Xử lý lỗi

| Tình huống | Kết quả |
|---|---|
| Không phải CEO | `403 forbidden` (từ `require_ceo` có sẵn) |
| `date_from > date_to` | Không lỗi — trả list rỗng nếu không có event nào giao nhau trong khoảng không hợp lệ |
| Không truyền `date_from`/`date_to` | Trả 200 dòng gần nhất toàn bộ lịch sử |

---

## 8. Testing

TDD, test trước code sau, mỗi task 1 commit:

- `backend/tests/test_audit_service.py`: seed đủ 5 loại event (1 task update, 1 login event, 1 instruction edit, 1 skill edit, 1 account event) → cả 5 xuất hiện đúng trong kết quả với đúng `type`/`summary`; lọc `date_from`/`date_to` đúng biên; non-CEO gọi → 403; sort đúng thứ tự mới nhất trước; `actor_name`/`target_name` resolve đúng; seed 205 dòng cùng loại → kết quả đúng 200 dòng, đúng 200 dòng mới nhất (không phải 200 dòng đầu tiên); `offboard_user` sinh CẢ 2 event `locked` và `offboarded` (không phải lỗi trùng); `change_role` chỉ đổi `manager_id` (không đổi role) vẫn sinh `AccountEvent(event_type="role_changed")`.
- `backend/tests/test_audit_api.py`: REST round-trip qua httpx, 403 cho non-CEO.
- `backend/tests/test_agent_tools_audit.py`: tool đăng ký, không sensitive, gọi qua `call_tool` trả đúng danh sách.
- Migration: `alembic revision --autogenerate -m "..."` rồi `alembic upgrade head` trên DB dev, xác nhận sạch (không có Enum type).
- Full pytest + `python scripts/export_openapi.py` (route mới → đổi contract).

---

## Self-review (đã chạy)

- **Placeholder scan:** không có TBD; giới hạn 200 dòng, cách tính `detail` cho từng loại event đã chốt cụ thể qua brainstorming.
- **Nhất quán nội bộ:** quyền CEO-only áp dụng nhất quán ở cả service (`require_ceo`) lẫn không có đường nào bỏ sót; `workspace_id` lọc ở cả 5 query nguồn.
- **Phạm vi:** đủ nhỏ cho 1 implementation plan — ước lượng 2-3 task (model+write-hook trong auth_service, service gộp+REST, tool chat). FE cố ý tách plan riêng.
- **Ambiguity check:** đã chốt rõ "1 timeline hợp nhất không tách 4 endpoint", "chỉ lọc theo ngày không lọc loại/người", "gộp cả offboard/change_role vào AccountEvent", "offboard sinh 2 event không phải lỗi trùng", "event_type dùng String không Enum (học từ bugfix 12cce73)" — không còn chỗ hiểu 2 nghĩa.
