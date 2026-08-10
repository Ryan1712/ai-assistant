---
agent: expo-mobile-lead
task_id: "4.1"
sprint: 4
title: Chọn project mở chat khóa ngữ cảnh — tap thẻ gọi createConversation scoped
description: Thêm luồng mở chat scoped theo project từ danh sách projects; banner khóa ngữ cảnh trong chat; chevron riêng xổ task
status: COMPLETE
started: 2026-08-08
completed: 2026-08-08
skills_used: []
---

## Progress

- [x] Read state file và điền description
- [x] Cập nhật Conversation type + createConversation signature (chat.ts)
- [x] Tạo ProjectScopeBanner component (src/ui/ProjectScopeBanner.tsx)
- [x] Tách ProjectCard ra file riêng (app/main/ProjectCard.tsx) — hook enforce 1 component/file
- [x] Refactor ProjectCard — tap body mở chat, Pressable chevron (sibling) xổ task
- [x] Cập nhật chat.tsx — banner khi conv có project_id, fetch tên project ngầm
- [x] Cập nhật test NewChatFab (thêm project_id vào Conversation mock)
- [x] Tạo test ProjectChat.test.tsx (8 tests)
- [x] tsc: CLEAN, jest: 47/47 GREEN

## Files Modified

| File | Action | Notes |
|------|--------|-------|
| `frontend/src/api/chat.ts` | MODIFY | Thêm `project_id: string \| null` vào Conversation; đổi createConversation sang opts object |
| `frontend/src/ui/ProjectScopeBanner.tsx` | CREATE | Component banner hiển thị khi chat scoped vào project |
| `frontend/app/main/ProjectCard.tsx` | CREATE | Tách ra từ projects.tsx; tap body → mở chat; Pressable chevron (sibling) → toggle task |
| `frontend/app/main/projects.tsx` | MODIFY | Bỏ ProjectCard inline, import từ ProjectCard.tsx |
| `frontend/app/main/chat.tsx` | MODIFY | Import listProjects + ProjectScopeBanner; thêm state conversationProjectId + projectName; hiển thị banner |
| `frontend/__tests__/NewChatFab.test.tsx` | MODIFY | Thêm `project_id: null` vào Conversation mock |
| `frontend/__tests__/ProjectChat.test.tsx` | CREATE | 8 tests: ProjectCard tap/chevron/error + ProjectScopeBanner |

## Completion Notes

**Quyết định thiết kế chính:**

1. **Chevron là Pressable (không phải TouchableOpacity)**: RNTL v14's `fireEvent.press` checks `onStartShouldSetResponder()` on the nearest touch responder via `isEventEnabled()`. When TouchableOpacity/Pressable has no visible children (Ionicons mocked to null in tests), the responder check returns false, blocking the event. `Pressable` exposes `onPress` directly on the host View prop, bypassing this. Production behavior identical.

2. **Chevron là SIBLING (không nested)**: Tránh nested-touchable race condition. Cấu trúc: `topRow View` chứa `[TouchableOpacity flex-1 | Pressable chevron]` cạnh nhau.

3. **fireEvent.press là async**: Phải `await fireEvent.press(...)` khi test state thay đổi synchronously — nếu không, synchronous `expect` chạy trước `act` flush xong. Ghi nhớ cho các test sau.

4. **Banner lấy tên project**: Gọi `listProjects()` ngầm sau khi load conversation, không block luồng chính. Hiển thị "đang tải..." khi chờ, fallback không crash nếu lỗi.

5. **Một component = một file**: Hook enforce chia `ProjectCard` ra `ProjectCard.tsx` riêng.

**Kết quả:**
- `tsc --noEmit` → CLEAN
- `jest --ci` → 47/47 GREEN (4 suites: ChatRow 11, NewChatFab 9, chatUtils 17, ProjectChat 8)
