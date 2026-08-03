---
agent: expo-mobile-lead
task_id: "2.1"
sprint: 2
title: Thêm lối vào "Cuộc trò chuyện mới" — FAB + drawer entry
description: Thêm FAB toàn cục và drawer entry để mở cuộc trò chuyện mới, ẩn FAB khi đang ở màn Chat
status: COMPLETE
started: 2026-08-02
completed: 2026-08-02
skills_used: []
---

## Progress

- [x] Read state file and filled `description:` field above
- [x] Đọc DESIGN.md, theme.ts, feature file, navigation files
- [x] Tạo `src/navigation/navigationRef.ts` — module-level NavigationContainerRef
- [x] Tạo `src/navigation/routeUtils.ts` — hàm thuần getActiveLeafRoute (testable)
- [x] Tạo `src/ui/NewChatFab.tsx` — FAB component với safe-area + tokens
- [x] Tạo `src/navigation/GlobalFab.tsx` — logic ẩn/hiện theo navigation state
- [x] Sửa `src/navigation/MainNavigator.tsx` — wrap View + render GlobalFab
- [x] Sửa `src/navigation/DrawerContent.tsx` — thêm nút "Cuộc trò chuyện mới"
- [x] Sửa `App.tsx` — đăng ký navigationRef với NavigationContainer
- [x] Tạo `__tests__/NewChatFab.test.tsx` — 9 tests (6 unit + 3 component)
- [x] `npx tsc --noEmit` → SẠCH
- [x] `npm test` → 18/18 GREEN
- [x] Review fixes: type.bodyStrong token, StyleSheet.create root style, GlobalFab tests
- [x] `npx tsc --noEmit` → SẠCH (sau review)
- [x] `npm test` → 21/21 GREEN (sau review)

## Files Modified

| File | Action | Notes |
|------|--------|-------|
| `frontend/src/navigation/navigationRef.ts` | CREATE | createNavigationContainerRef — dùng cho CommonActions.navigate từ FAB |
| `frontend/src/navigation/routeUtils.ts` | CREATE | getActiveLeafRoute — hàm thuần, đệ quy nested state |
| `frontend/src/ui/NewChatFab.tsx` | CREATE | FAB component; position absolute; safe-area; tokens; accessibilityRole=button |
| `frontend/src/navigation/GlobalFab.tsx` | CREATE | useNavigationState → ẩn khi Chat, hiện khi route khác |
| `frontend/src/navigation/MainNavigator.tsx` | MODIFY | Wrap Stack.Navigator trong View; render GlobalFab |
| `frontend/src/navigation/DrawerContent.tsx` | MODIFY | Thêm nút pill xanh "Cuộc trò chuyện mới" trên MENU |
| `frontend/App.tsx` | MODIFY | ref={navigationRef} vào NavigationContainer (1 dòng) |
| `frontend/__tests__/NewChatFab.test.tsx` | CREATE | 9 tests: 6 unit (getActiveLeafRoute) + 3 component (render/press) |

## Completion Notes

**Quyết định thiết kế:**
- `routeUtils.ts` tách riêng khỏi navigator để hàm thuần `getActiveLeafRoute` test được dễ dàng — giải quyết yêu cầu "hàm thuần tách khỏi hàm có side-effect".
- `GlobalFab` là component riêng (frontend standard #1: 1 file = 1 component), import vào `MainNavigator`.
- `GlobalFab` dùng `useNavigationState` từ Root Stack context (context gần nhất bên trong `MainNavigator` là Root Stack) — state object chứa đầy đủ nested state của Main Stack + Drawer → đệ quy tìm leaf.
- FAB navigation dùng `CommonActions.navigate({ name: 'Chat', params: {} })` dispatch qua `navigationRef` — action bubble xuống nested navigators, tìm 'Chat' trong Drawer.
- DrawerContent: nút pill xanh primary (`radius.pill`) trên MENU, gọi `openChat()` hiện có (không id = chat mới).
- `App.tsx` thay đổi tối thiểu: chỉ thêm `ref={navigationRef}` + 1 import.

**Kết quả kiểm tra:**
- `tsc --noEmit` → 0 lỗi
- `npm test` → 18/18 tests GREEN (9 new + 9 existing ChatRow)
