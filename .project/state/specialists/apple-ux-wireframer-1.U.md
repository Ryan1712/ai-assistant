---
agent: vfm-agent-company:apple-ux-wireframer
task_id: 1.U
sprint: 1
title: Wireframe màn hình lỗi + bong bóng lỗi trong chat
description: Thiết kế ASCII wireframe 2 biến thể ErrorBoundary fallback và bong bóng lỗi API trong khung chat, dùng token Grammarly theme.
status: COMPLETE
started: 2026-07-27
completed: 2026-07-27
skills_used: [ux-wireframing]
---

## Progress

- [x] Đọc state file và điền description
- [x] Đọc DESIGN.md, theme.ts, AGENTS.md, sprint-1.md, architecture.md, chat.tsx
- [x] Tạo .project/wireframes/screens/error-fallback.md
- [x] Tạo .project/wireframes/screens/chat-error-bubble.md
- [x] Cập nhật sprint-1.md Task 1.U → [COMPLETE]
- [x] Điền Completion Notes

## Files Modified

| File | Action | Notes |
|------|--------|-------|
| .project/wireframes/screens/error-fallback.md | CREATE | A1 + A2 |
| .project/wireframes/screens/chat-error-bubble.md | CREATE | B1–B5 |
| .project/sprints/sprint-1.md | EDIT | Task 1.U → COMPLETE |

## Completion Notes

**Quyết định chính**:
1. Mã sự cố (A1): Có — 8 ký tự, kiểu caption/muted, dưới divider. Dùng khi gọi support. Không có trong A2.
2. Nút A2 dùng ghost neutral (không phải primary) — fallback không phải trạng thái thành công.
3. Error bubble (B1/B2) thiết kế là card `radius.md` — khác hẳn với tool-use pill. Phân biệt rõ bằng hình dạng + màu nền.
4. Text người dùng giữ trong input (setInput hiện tại đã đúng) — không cần "pending bubble" riêng.
5. Offline kéo dài: dùng sticky warning banner (vàng) thay vì bong bóng đỏ lặp — tránh noise.
6. Câu lỗi "Hệ thống đang có lỗi, vui lòng thử lại." giữ nguyên 100% như client chốt.

**Token thiếu cần thêm vào theme.ts**:
- `colors.dangerBorder` — viền error bubble (thiếu, cặp warningBorder/confirmBorder đã có)
- `colors.dangerText` — chữ body trên dangerBg (colors.danger trên dangerBg chỉ đạt ~2.3:1, không đủ WCAG AA)

**Rủi ro**: Dev cần thêm token vào theme.ts TRƯỚC khi triển khai Task 1.4, không được hardcode hex.
