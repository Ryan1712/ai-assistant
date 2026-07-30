---
agent: expo-mobile-lead
task_id: "1.2"
sprint: 1
title: "Cắt re-render và scroll thừa khi AI streaming token"
description: Memo hoá renderItem/renderRow và throttle scrollToEnd trong chat.tsx để giảm jank khi AI streaming token
status: IN_PROGRESS
started: 2026-07-30
completed:
skills_used: []
---

## Progress

- [x] Read state file and filled `description:` field above
- [ ] Đọc chat.tsx toàn bộ
- [ ] Tách ChatRow component con + React.memo
- [ ] Bọc handlers bằng useCallback
- [ ] Throttle scrollToEnd với useRef timestamp
- [ ] Thêm FlatList props (maxToRenderPerBatch, windowSize) nếu an toàn
- [ ] Viết/chỉnh test
- [ ] npx tsc --noEmit GREEN
- [ ] npm test GREEN
- [ ] Commit

## Files Modified

| File | Action | Notes |
|------|--------|-------|
| (update as you go) | | |

## Completion Notes

[FILL when done: key decisions, test results, blockers resolved]
