# Thiết kế — Đổi vai trò / đổi manager (cho người vẫn đang làm việc)

**Ngày:** 2026-07-15 · **Trạng thái:** Đã duyệt qua brainstorming · **Spec chức năng:** [funtional-plan.md](../../../funtional-plan.md) §8 ("Xử lý khi nhân sự nghỉ hoặc đổi vai trò: bàn giao task + khóa tài khoản")

Lấp nốt phần còn lại của khoảng trống ở funtional-plan §8 — phần "đổi vai trò" đã bị loại khỏi phạm vi [offboarding](2026-07-14-offboarding-design.md) (xem spec đó §1, "Ngoài phạm vi"). Khác offboarding: người này **vẫn tiếp tục làm việc** — không khóa tài khoản, không đụng vào `TaskAssignee` của chính họ.

---

## 1. Phạm vi & Ranh giới

**Trong phạm vi:**
- 1 hàm service mới `auth_service.change_role(db, actor, target_id, *, new_role=None, new_manager_id=None, successor_id=None) -> dict`.
- Đổi `role` và/hoặc đổi `manager_id` của 1 người đang hoạt động, trong cùng 1 lần gọi.
- Nếu việc đổi role khiến target **rời khỏi vai trò manager** trong khi đang có direct report và/hoặc đang sở hữu project (`owner_id`) → bắt buộc `successor_id` để bàn giao 2 thứ đó (tái dùng ý tưởng successor của offboarding, nhưng **không đụng `TaskAssignee`** — target vẫn giữ nguyên task của chính họ vì vẫn đang làm việc).
- REST `POST /api/v1/users/{user_id}/change-role` + tool chat `change_user_role` (`sensitive=True`).

**Ngoài phạm vi (cố ý, YAGNI):**
- **Đổi `is_root`** — cờ root CEO bất biến, không có tham số nào trong hàm này đụng tới nó.
- **Tự đổi role/manager của chính actor** — không cần chặn riêng, tự động bị chặn bởi rule quyền (mục 3) giống offboarding tự chặn tự-offboard.
- **Cycle detection tổng quát cho `manager_id`** (vd A→B→A qua nhiều bước) — hệ thống chỉ có 1 cấp phân cấp thực tế (`visible_user_ids`/`direct_report_ids` không đệ quy sâu hơn 1 cấp), nên chỉ cần chặn `new_manager_id == target_id`, không cần duyệt cây.
- **Bàn giao `SkillGrant`** — như offboarding, không transfer.
- **Thông báo riêng cho từng direct report bị đổi manager** — chỉ 1 notify tóm tắt cho successor (nếu có), giống offboarding.
- **FE UI** — không có màn hình (tiền lệ: `lock_user`/`offboard_user` cũng chỉ REST/tool).
- **Không thêm migration/bảng mới** — tái dùng nguyên `User.role`, `User.manager_id`, `Project.owner_id`.

---

## 2. Quy tắc quyền (permission)

Mở rộng — không sửa — `_check_lock_permission` sẵn có. Viết hàm riêng `_check_role_change_permission(actor, target, new_role)` trong `auth_service.py`:

- `require_ceo(actor)` — chỉ CEO gọi được (403 `forbidden`).
- Target khác workspace → 404 `user_not_found`.
- Target `is_root` → 403 `cannot_change_root_ceo` (root bất biến, không ai đổi được role/manager của root, kể cả actor là root khác... thực ra chỉ có 1 root/workspace nên trường hợp là actor tự đụng root chính mình, đã tự chặn qua rule "actor==target" phía dưới nếu áp dụng, nhưng để rõ ràng vẫn chặn cứng tại đây).
- Target hiện là `ceo`, **hoặc** `new_role == Role.ceo` → phải `actor.is_root` (403 `only_root_can_change_ceo`). Đây là điểm mở rộng so với `_check_lock_permission`: helper cũ chỉ xét role hiện tại của target, ở đây còn phải xét cả role **đích** (thăng ai đó thành CEO cũng nhạy cảm ngang việc đụng vào 1 CEO đang tồn tại).

---

## 3. Thiết kế hàm `change_role`

Đặt trong `app/services/auth_service.py`, ngay sau `offboard_user`:

```python
async def change_role(db: AsyncSession, actor: User, target_id: uuid_mod.UUID, *,
                      new_role: Role | None = None,
                      new_manager_id: uuid_mod.UUID | None = None,
                      successor_id: uuid_mod.UUID | None = None) -> dict:
    if new_role is None and new_manager_id is None:
        raise HTTPException(422, "no_change_requested")

    target = await db.get(User, target_id)
    if target is None or target.workspace_id != actor.workspace_id:
        raise HTTPException(404, "user_not_found")
    _check_role_change_permission(actor, target, new_role)

    # new_manager_id: validate nếu có truyền
    if new_manager_id is not None:
        if new_manager_id == target_id:
            raise HTTPException(422, "invalid_manager")
        manager = await db.get(User, new_manager_id)
        if (manager is None or manager.workspace_id != actor.workspace_id
                or manager.role != Role.manager):
            raise HTTPException(422, "invalid_manager")

    resulting_role = new_role if new_role is not None else target.role
    resulting_manager_id = new_manager_id if new_manager_id is not None else target.manager_id
    if resulting_role == Role.employee and resulting_manager_id is None:
        raise HTTPException(422, "employee_requires_manager")

    reports_reassigned = 0
    projects_reassigned = 0
    leaving_manager = (new_role is not None and target.role == Role.manager
                       and new_role != Role.manager)

    if leaving_manager:
        has_reports = (await db.execute(select(User.id).where(
            User.workspace_id == actor.workspace_id, User.manager_id == target_id))).first()
        has_projects = (await db.execute(select(Project.id).where(
            Project.workspace_id == actor.workspace_id, Project.owner_id == target_id))).first()

        if has_reports or has_projects:
            if successor_id is None:
                raise HTTPException(422, "successor_required")
            successor = await db.get(User, successor_id)
            if successor is None or successor.workspace_id != actor.workspace_id:
                raise HTTPException(404, "user_not_found")
            if successor.id == target_id or successor.status == UserStatus.locked:
                raise HTTPException(422, "invalid_successor")

            result = await db.execute(update(User).where(
                User.workspace_id == actor.workspace_id, User.manager_id == target_id
            ).values(manager_id=successor_id))
            reports_reassigned = result.rowcount or 0

            result = await db.execute(update(Project).where(
                Project.workspace_id == actor.workspace_id, Project.owner_id == target_id
            ).values(owner_id=successor_id))
            projects_reassigned = result.rowcount or 0

            await notify(db, workspace_id=actor.workspace_id, recipient_id=successor_id,
                        type="management_handoff",
                        payload={"from_user": str(target_id),
                                 "reports_reassigned": reports_reassigned,
                                 "projects_reassigned": projects_reassigned})

    if new_role is not None:
        target.role = new_role
    if new_manager_id is not None:
        target.manager_id = new_manager_id

    await notify(db, workspace_id=actor.workspace_id, recipient_id=target_id,
                type="role_changed",
                payload={"role": target.role.value,
                         "manager_id": str(target.manager_id) if target.manager_id else None})
    await db.commit()

    return {"role": target.role.value,
            "manager_id": str(target.manager_id) if target.manager_id else None,
            "successor_id": str(successor_id) if successor_id else None,
            "reports_reassigned": reports_reassigned,
            "projects_reassigned": projects_reassigned}
```

Ghi chú thiết kế:
- **Không đụng `TaskAssignee`** — khác biệt cốt lõi so với `offboard_user`. Target vẫn đang làm việc, giữ nguyên mọi task đang được giao dù role đổi.
- **`successor_id` chỉ bắt buộc khi thực sự cần** — nếu target đổi role nhưng hiện không có direct report/owned project (vd employee → manager, hoặc manager → employee nhưng không quản lý ai), không cần successor.
- **Đổi role và đổi manager cùng lúc** — vd demote manager → employee kèm luôn `new_manager_id` (người employee đó giờ báo cáo ai) trong 1 lệnh gọi, đúng với `employee_requires_manager` check ở trên (dùng `resulting_manager_id` tính trước khi ghi, không chỉ nhìn `target.manager_id` cũ).
- **2 notify** — 1 cho target (biết mình vừa bị đổi role/manager), 1 cho successor nếu có bàn giao (giống pattern `offboard_handoff`, đổi tên event thành `management_handoff` vì không liên quan khóa tài khoản).
- **Không idempotent-check đặc biệt** — gọi lại với cùng tham số vẫn chạy được, chỉ là no-op thực chất (role/manager_id đã đúng giá trị đó rồi), không cần guard riêng.

---

## 4. REST endpoint & Tool

### `POST /api/v1/users/{user_id}/change-role`

`app/api/users.py`, đặt cạnh `/offboard`:

```python
class ChangeRoleIn(BaseModel):
    new_role: Role | None = None
    new_manager_id: uuid.UUID | None = None
    successor_id: uuid.UUID | None = None

@router.post("/{user_id}/change-role")
async def change_role(user_id: uuid.UUID, body: ChangeRoleIn,
                      actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    return await auth_service.change_role(db, actor, user_id, new_role=body.new_role,
                                          new_manager_id=body.new_manager_id,
                                          successor_id=body.successor_id)
```

`ChangeRoleIn` thêm vào `app/schemas.py`.

### Tool `change_user_role` (`app/agent/tools.py`)

```python
class ChangeUserRoleToolIn(BaseModel):
    user_id: uuid.UUID
    new_role: Role | None = None
    new_manager_id: uuid.UUID | None = None
    successor_id: uuid.UUID | None = None

async def _change_user_role(db, actor, body: ChangeUserRoleToolIn) -> dict:
    return await auth_service.change_role(db, actor, body.user_id, new_role=body.new_role,
                                          new_manager_id=body.new_manager_id,
                                          successor_id=body.successor_id)

_register("change_user_role",
          "Đổi vai trò (employee/manager/ceo) và/hoặc đổi người quản lý trực tiếp của 1 người "
          "ĐANG làm việc (không khóa tài khoản, không đụng task đang được giao của họ). Nếu đổi "
          "khỏi vai trò manager mà người đó đang có nhân viên báo cáo hoặc đang sở hữu project, "
          "PHẢI cung cấp successor_id để bàn giao. Chỉ CEO gọi được; đổi liên quan tới vai trò CEO "
          "(thăng ai đó thành CEO, hoặc đổi role của 1 CEO khác) chỉ root CEO gọi được — hành động "
          "nhạy cảm, hệ thống TỰ hiện bước xác nhận khi gọi tool, cứ gọi ngay đừng hỏi trước.",
          ChangeUserRoleToolIn, _change_user_role, sensitive=True)
```

---

## 5. Xử lý lỗi

| Tình huống | Kết quả |
|---|---|
| Không truyền `new_role` lẫn `new_manager_id` | `422 no_change_requested` |
| Không phải CEO gọi | `403 forbidden` |
| Target không tồn tại/khác workspace | `404 user_not_found` |
| Target là root CEO | `403 cannot_change_root_ceo` |
| Target hiện là CEO khác (không phải root), actor không phải root | `403 only_root_can_change_ceo` |
| `new_role == ceo`, actor không phải root | `403 only_root_can_change_ceo` |
| `new_manager_id == target_id` | `422 invalid_manager` |
| `new_manager_id` không tồn tại/khác workspace/không phải role=manager | `422 invalid_manager` |
| Kết quả cuối cùng role=employee nhưng không có manager_id nào (mới hoặc cũ) | `422 employee_requires_manager` |
| Rời role manager, đang có direct report/owned project, không truyền `successor_id` | `422 successor_required` |
| `successor_id` không tồn tại/khác workspace | `404 user_not_found` |
| `successor_id == target_id`, hoặc successor đã bị khóa | `422 invalid_successor` |
| Rời role manager nhưng không có direct report/owned project nào | Đổi bình thường, `reports_reassigned`/`projects_reassigned` = 0, không cần successor |

---

## 6. Testing

TDD, test trước code sau, mỗi task 1 commit — theo đúng pattern các plan trước:

- `backend/tests/test_change_role_service.py`:
  - Employee/manager gọi → 403.
  - CEO đổi role employee → manager (promotion, không cần successor) → thành công.
  - CEO đổi `new_manager_id` một mình (không đổi role) → cập nhật đúng, không đụng gì khác.
  - CEO demote 1 manager có direct report + owned project, không truyền successor → 422 `successor_required`.
  - CEO demote manager → employee kèm successor → direct report + project chuyển sang successor; `TaskAssignee` của target giữ nguyên (test rõ điểm khác biệt với offboard).
  - Demote manager → employee kèm successor, đồng thời truyền `new_manager_id` cho chính target → cả 2 thay đổi áp dụng đúng, không lẫn lộn giữa "manager mới của target" và "successor nhận bàn giao".
  - Đổi role thành employee mà không có manager nào (mới lẫn cũ) → 422 `employee_requires_manager`.
  - `new_manager_id` trỏ tới người role != manager → 422 `invalid_manager`.
  - `new_manager_id == target_id` → 422 `invalid_manager`.
  - Không truyền gì cả (`new_role=None, new_manager_id=None`) → 422 `no_change_requested`.
  - Đổi role target là root CEO → 403 `cannot_change_root_ceo`.
  - Đổi role 1 CEO khác (không phải root) bởi CEO thường → 403 `only_root_can_change_ceo`.
  - Thăng 1 employee thành CEO bởi CEO thường (không phải root) → 403 `only_root_can_change_ceo`.
  - Thăng 1 employee thành CEO bởi root CEO → thành công.
  - `successor_id` khác workspace/không tồn tại → 404; `successor_id == target_id` hoặc đã bị khóa → 422 (tái dùng case tương tự offboard).
- `backend/tests/test_agent_tools_change_role.py`: tool đăng ký, `sensitive=True`, gọi qua `call_tool` thành công + wrap lỗi 403 đúng dạng.
- `backend/tests/test_change_role_api.py`: REST endpoint qua httpx, các case chính (200 thành công, 403, 422 `successor_required`).
- Full pytest sau khi xong, `python scripts/export_openapi.py` (route mới → đổi contract).

---

## Self-review (đã chạy)

- **Placeholder scan:** không có TBD; mọi quyết định (phạm vi role+manager gộp chung, quyền CEO/root, ràng buộc `new_manager_id` phải role=manager, successor bắt buộc có điều kiện, không đụng TaskAssignee) đã chốt qua brainstorming.
- **Nhất quán nội bộ:** rule quyền không sửa `_check_lock_permission` cũ (offboarding vẫn dùng nguyên), chỉ thêm hàm riêng `_check_role_change_permission` — tránh side effect chéo giữa 2 tính năng. `workspace_id` lọc đúng mọi update (User/Project) theo quy ước CLAUDE.md, học từ bugfix `2b6ee87` của offboarding (tránh sót filter workspace).
- **Phạm vi:** đủ nhỏ cho 1 implementation plan — ước lượng 3 task (service function, REST + schema, tool + openapi), giống cấu trúc plan offboarding. Không migration.
- **Ambiguity check:** đã chốt rõ "successor chỉ bắt buộc khi rời role manager VÀ có dependents", "TaskAssignee không bị đụng", "new_manager_id phải role=manager", "employee luôn cần có manager_id kết quả cuối" — không còn chỗ hiểu 2 nghĩa.
