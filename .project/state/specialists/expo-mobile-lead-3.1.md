---
agent: expo-mobile-lead
task_id: "3.1"
sprint: 3
title: Chuyển chat sang mô hình ChatGPT — mỗi conversation là thread độc lập
description: Refactor màn chat từ timeline gộp sang single-conversation; nút new chat gọi createConversation rồi điều hướng với id mới
status: COMPLETE
started: 2026-08-08
completed: 2026-08-08
skills_used: []
---

## Progress

- [x] Read state file and filled `description:` field above
- [x] Tạo chatUtils.ts — trích xuất messagesToRows (no dividers), textOfMessage, labelForTool
- [x] Sửa chat.tsx — single-conv mode, bỏ timeline, bỏ olderCursor
- [x] Sửa DrawerContent.tsx — openChat async với createConversation
- [x] Sửa GlobalFab.tsx — onPress async với createConversation
- [x] Thêm test chatUtils.test.ts
- [x] Cập nhật NewChatFab.test.tsx cho GlobalFab flow mới
- [x] Chạy tsc + jest (3 suites, 39 tests — ALL GREEN)

## Files Modified

| File | Action | Notes |
|------|--------|-------|
| frontend/app/main/chatUtils.ts | CREATE | messagesToRows thuần, không cross-conv divider |
| frontend/app/main/chat.tsx | MODIFY | single-conv, bỏ timeline + olderCursor |
| frontend/src/navigation/DrawerContent.tsx | MODIFY | openChat async, MENU Chat → {id:undefined} |
| frontend/src/navigation/GlobalFab.tsx | MODIFY | onPress async createConversation |
| frontend/__tests__/chatUtils.test.ts | CREATE | unit test messagesToRows |
| frontend/__tests__/NewChatFab.test.tsx | MODIFY | update GlobalFab test |

## Completion Notes

**Quyết định thiết kế chính:**
- `historyMode` chuyển từ useState sang derived const `const historyMode = !!requestedId` — loại bỏ race condition giữa params và state, luôn nhất quán với route.
- Bỏ hoàn toàn `getTimeline()`, `olderCursor`, `hasMoreOlder`, `loadOlder` — conversation giới hạn ~150 msg nên `listMessages(convId)` load 1 lần là đủ.
- `messagesToRows` tách ra `chatUtils.ts` để unit test được mà không cần mount component. Hàm đơn giản hơn: bỏ `prevConv` tracking và divider cross-conv.
- GlobalFab: fallback về `{ id: undefined }` khi `createConversation` lỗi mạng — vẫn điều hướng về active conv thay vì crash.
- DrawerContent MENU "Chat": `navigate("Chat", { id: undefined })` thay vì `navigate("Chat")` không params — đảm bảo params thay đổi khi đang xem cuộc cũ.

**Lưu ý cho chủ sản phẩm:**
- Timeline Phase 5 (getTimeline cross-conv) đã bị xóa hoàn toàn. Nếu tương lai cần "lịch sử toàn bộ hội thoại" (cross-conv) thì phải implement lại riêng ở màn khác.
- Cuộc cũ (có id, không archived) vẫn chat được — submit gửi vào conv đó, không phải active conv.

**Test:** 3 suites, 39 tests — tsc clean, jest ALL GREEN.
