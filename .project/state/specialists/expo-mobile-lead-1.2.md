---
agent: expo-mobile-lead
task_id: "1.2"
sprint: 1
title: "Cắt re-render và scroll thừa khi AI streaming token"
description: Memo hoá renderItem/renderRow và throttle scrollToEnd trong chat.tsx để giảm jank khi AI streaming token
status: COMPLETE
started: 2026-07-30
completed: 2026-07-30
skills_used: [React.memo, useCallback, useRef throttle, jest-expo, RNTL v14]
---

## Progress

- [x] Read state file and filled `description:` field above
- [x] Đọc chat.tsx toàn bộ
- [x] Tách ChatRow component con + React.memo (→ ChatRow.tsx)
- [x] Bọc handlers bằng useCallback (submit, toggleAudioBubble, onRetry, renderItem)
- [x] Throttle scrollToEnd với useRef timestamp (100ms + trailing call)
- [x] Thêm FlatList props (maxToRenderPerBatch={10}, windowSize={5})
- [x] Viết 9 test cho ChatRow (tất cả XANH)
- [x] npx tsc --noEmit GREEN
- [x] npm test GREEN (9/9)
- [x] Commit 83f2014

## Files Modified

| File | Action | Notes |
|------|--------|-------|
| frontend/app/main/chat.tsx | Modified | Bỏ renderRow, thêm useCallback cho handlers và renderItem, throttle scrollToEnd |
| frontend/app/main/ChatRow.tsx | Created | React.memo component cho tất cả 6 loại row |
| frontend/app/main/chatTypes.ts | Created | Kiểu Row dùng chung — tránh circular import |
| frontend/__tests__/ChatRow.test.tsx | Created | 9 test RNTL v14 (async render) |
| frontend/package.json | Modified | Thêm jest-expo, @testing-library/react-native, test-renderer, jest, @react-native/jest-preset, @types/jest vào devDependencies |
| frontend/tsconfig.json | Modified | Thêm "types": ["jest"] |

## Completion Notes

- PostToolUse hook bắt buộc "one component per file" → không được định nghĩa ChatRow trong chat.tsx, phải tách ra file riêng
- chatTypes.ts cần thiết để tránh circular import (Chat → ChatRow → chatTypes, không có chiều ngược)
- RNTL v14 breaking change: render() là async function → mọi test phải async và await render()
- RNTL v14 peer dep mới: `test-renderer` (khác react-test-renderer) — cần cài riêng
- jest-expo + jest + @react-native/jest-preset phải cài đầy đủ; expo install bị conflict peer deps → dùng npm install --legacy-peer-deps
