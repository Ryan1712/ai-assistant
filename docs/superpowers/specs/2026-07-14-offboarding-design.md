# Thiết kế — Offboarding (bàn giao task/project/nhân viên khi 1 người nghỉ)

**Ngày:** 2026-07-14 · **Trạng thái:** Đã duyệt qua brainstorming · **Spec chức năng:** [funtional-plan.md](../../../funtional-plan.md) §8 ("Xử lý khi nhân sự nghỉ hoặc đổi vai trò: bàn giao task + khóa tài khoản")

Lấp 1 trong các khoảng trống nêu ở funtional-plan §8. Phạm vi tách riêng: chỉ **offboarding** (nghỉ việc) = khóa tài khoản + bàn giao. "Đổi vai trò" (thăng chức, đổi team mà vẫn làm việc) là tính năng khác, không nằm trong spec này (chưa có yêu cầu rõ ràng cho luồng đó).

---

## 1. Phạm vi & Ranh giới

**Trong phạm vi:**
- 1 hàm service mới `auth_service.offboard_user(db, actor, target_id, successor_id=None) -> dict` — **tái dùng nguyên** `lock_user()` đã có (không viết lại logic khóa/permission/revoke token/notify).
- Nếu có `successor_id`: bàn giao cho **đúng 1 người** — tất cả `TaskAssignee` của người nghỉ, tất cả `Project.owner_id` họ đang giữ, và (nếu họ là manager) tất cả direct report (`User.manager_id`) đều chuyển sang successor.
- 1 thông báo tóm tắt duy nhất gửi cho successor qua `notify()` có sẵn.
- REST `POST /api/v1/users/{user_id}/offboard` + tool chat `offboard_user` (sensitive=True, giống `lock_user`).

**Ngoài phạm vi (cố ý, YAGNI):**
- **"Đổi vai trò"** (đổi `role`/`manager_id` cho người vẫn đang làm việc, không khóa tài khoản) — endpoint update-role/update-manager chưa tồn tại, không thêm trong spec này. Nếu cần sau, đó là 1 spec riêng.
- **Bàn giao `SkillGrant`** (skill đã cấp cho người nghỉ) — không transfer, vô hại vì tài khoản đã khóa không đăng nhập được.
- **Bàn giao chia nhỏ theo loại** (vd task cho người A, direct report cho người B) — chỉ 1 successor cho tất cả, theo quyết định đã chốt.
- **Thông báo riêng cho từng direct report bị đổi manager** — chỉ successor nhận 1 thông báo tóm tắt số liệu, không thông báo từng nhân viên bị ảnh hưởng.
- **FE UI** — không có màn hình nào (khớp tiền lệ: `lock_user`/`unlock_user` cũng chỉ có REST/tool, không có FE, đây là hành động admin hiếm khi dùng).
- **Không thêm migration/bảng mới** — tái dùng nguyên `User.status`, `TaskAssignee`, `Project.owner_id`, `User.manager_id` đã có.

---

## 2. Thiết kế hàm `offboard_user`

Thêm vào `app/services/auth_service.py` (cạnh `lock_user`/`unlock_user`/`_check_lock_permission` đã có ở đó — tái dùng trực tiếp, không export `_check_lock_permission` sang file khác):

```python
async def offboard_user(db: AsyncSession, actor: User, target_id: uuid_mod.UUID,
                        successor_id: uuid_mod.UUID | None = None) -> dict:
    await lock_user(db, actor, target_id)  # tái dùng nguyên: permission check + khóa + revoke token + notify(account_locked) + commit

    tasks_reassigned = 0
    projects_reassigned = 0
    reports_reassigned = 0

    if successor_id is not None:
        successor = await db.get(User, successor_id)
        if successor is None or successor.workspace_id != actor.workspace_id:
            raise HTTPException(404, "user_not_found")
        if successor.id == target_id or successor.status == UserStatus.locked:
            raise HTTPException(422, "invalid_successor")

        # Bàn giao task — xóa assignee cũ, thêm successor nếu chưa được giao task đó
        rows = (await db.execute(
            select(TaskAssignee).where(TaskAssignee.user_id == target_id))).scalars().all()
        for row in rows:
            existing = await db.execute(select(TaskAssignee.id).where(
                TaskAssignee.task_id == row.task_id, TaskAssignee.user_id == successor_id))
            if existing.first() is None:
                db.add(TaskAssignee(workspace_id=actor.workspace_id, task_id=row.task_id,
                                    user_id=successor_id))
            await db.delete(row)
            tasks_reassigned += 1

        # Bàn giao project owner
        result = await db.execute(update(Project).where(
            Project.workspace_id == actor.workspace_id, Project.owner_id == target_id
        ).values(owner_id=successor_id))
        projects_reassigned = result.rowcount or 0

        # Bàn giao direct report (nếu người nghỉ là manager)
        result = await db.execute(update(User).where(
            User.workspace_id == actor.workspace_id, User.manager_id == target_id
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
```

Ghi chú thiết kế:
- **Permission**: hoàn toàn thừa hưởng từ `lock_user`/`_check_lock_permission` — chỉ CEO gọi được (403 nếu không), không khóa được root CEO (403 `cannot_lock_root_ceo`), CEO thường không khóa được CEO khác (403 `only_root_can_lock_ceo`). Không viết thêm rule quyền nào mới.
- **Không cần chặn "actor tự offboard chính mình"** — logic thừa hưởng từ `_check_lock_permission` đã tự loại trừ: CEO root tự offboard bị chặn bởi `target.is_root`; CEO thường tự offboard bị chặn bởi `only_root_can_lock_ceo` (trừ khi actor chính là root — nhưng root luôn bị chặn bởi check `is_root` trước đó).
- **Idempotent giống `lock_user`** — gọi `offboard_user` trên người đã bị khóa từ trước vẫn chạy được (không lỗi "already locked"), hữu ích nếu CEO khóa tay trước rồi mới bàn giao riêng sau.
- **`successor_id` optional** — không truyền thì chỉ khóa, không bàn giao gì (hợp lý cho người không có task/project/report gì để giao).
- **N+1 khi lặp `TaskAssignee`** — chấp nhận được vì đây là hành động CEO-only, tần suất thấp (giống các N+1 khác đã chấp nhận trong codebase ở Plan 2/4).

---

## 3. REST endpoint & Tool

### `POST /api/v1/users/{user_id}/offboard`

`app/api/users.py`, đặt cạnh `/lock`/`/unlock`:

```python
class OffboardIn(BaseModel):
    successor_id: uuid.UUID | None = None

@router.post("/{user_id}/offboard")
async def offboard_user(user_id: uuid.UUID, body: OffboardIn,
                        actor: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    return await auth_service.offboard_user(db, actor, user_id, body.successor_id)
```

`OffboardIn` thêm vào `app/schemas.py`. Response trả nguyên dict từ service (không cần `response_model` Pydantic riêng — 4 field đơn giản, đủ rõ qua dict).

### Tool `offboard_user` (`app/agent/tools.py`)

```python
class OffboardUserToolIn(BaseModel):
    user_id: uuid.UUID
    successor_id: uuid.UUID | None = None

async def _offboard_user(db, actor, body: OffboardUserToolIn) -> dict:
    return await auth_service.offboard_user(db, actor, body.user_id, body.successor_id)

_register("offboard_user",
          "Cho 1 người nghỉ việc — khóa tài khoản (đăng xuất mọi thiết bị) và bàn giao toàn bộ "
          "task/project/nhân viên báo cáo trực tiếp (nếu có) cho 1 người kế thừa (chỉ CEO, hành "
          "động nhạy cảm - hệ thống TỰ hiện bước xác nhận khi gọi tool, cứ gọi ngay đừng hỏi trước).",
          OffboardUserToolIn, _offboard_user, sensitive=True)
```

Đăng ký `sensitive=True` giống `lock_user` — blast radius lớn hơn (khóa + bàn giao hàng loạt), càng cần xác nhận 2 bước.

---

## 4. Xử lý lỗi

| Tình huống | Kết quả |
|---|---|
| Không phải CEO gọi | `403 forbidden` (thừa hưởng từ `require_ceo` trong `_check_lock_permission`) |
| Target không tồn tại/khác workspace | `404 user_not_found` |
| Target là root CEO | `403 cannot_lock_root_ceo` |
| Target là CEO khác, actor không phải root | `403 only_root_can_lock_ceo` |
| `successor_id` không tồn tại/khác workspace | `404 user_not_found` |
| `successor_id` == `target_id`, hoặc successor đã bị khóa | `422 invalid_successor` |
| Không truyền `successor_id` | Chỉ khóa, không bàn giao — `tasks_reassigned`/`projects_reassigned`/`reports_reassigned` đều 0 |
| Target đã bị khóa từ trước | Vẫn chạy được (idempotent), khóa lại + bàn giao nếu có successor |

---

## 5. Testing

Theo đúng pattern TDD xuyên suốt các plan trước — test trước, code sau, mỗi task 1 commit:

- `backend/tests/test_offboard_service.py`:
  - Employee/manager gọi → 403.
  - CEO offboard employee không successor → status=locked, mọi count=0.
  - CEO offboard employee có task được giao + successor → task chuyển sang successor, không tạo dòng trùng nếu successor đã được giao sẵn task đó (respect `uq_task_assignee`).
  - CEO offboard người đang là project owner + successor → `Project.owner_id` cập nhật.
  - CEO offboard 1 manager có direct report + successor → report đó `manager_id` cập nhật sang successor.
  - `successor_id` khác workspace/không tồn tại → 404.
  - `successor_id == target_id` → 422.
  - successor đã bị khóa → 422.
  - Offboard root CEO → 403; CEO thường offboard CEO khác → 403 (2 case thừa hưởng, test lại để khóa hành vi).
- `backend/tests/test_agent_tools_offboard.py`: tool đăng ký, `sensitive=True`, gọi qua `call_tool` thành công + wrap lỗi 403 đúng dạng.
- `backend/tests/test_offboard_api.py`: REST endpoint qua httpx, các case 403/404/422 + thành công.
- Full pytest sau khi xong, `python scripts/export_openapi.py` (đổi contract vì thêm route mới).

---

## Self-review (đã chạy)

- **Placeholder scan:** không có TBD; mọi quyết định (1 successor duy nhất, không bàn giao skill grant, chỉ notify successor, không FE, tái dùng `lock_user`) đã chốt qua brainstorming.
- **Nhất quán nội bộ:** không thêm rule quyền mới — toàn bộ permission thừa hưởng từ `_check_lock_permission` đã có; `workspace_id` lọc đúng mọi update (Project/User) theo quy ước CLAUDE.md.
- **Phạm vi:** đủ nhỏ cho 1 implementation plan — ước lượng 3 task (service function, REST + schema, tool + openapi). Không migration.
- **Ambiguity check:** đã chốt rõ "không transfer skill grant", "chỉ 1 notify tóm tắt", "successor optional = chỉ khóa không bàn giao", "idempotent nếu đã khóa từ trước" — không còn chỗ hiểu 2 nghĩa.
