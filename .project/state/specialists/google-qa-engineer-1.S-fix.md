---
agent: vfm-agent-company:google-qa-engineer
task_id: 1.S-fix
sprint: 1
title: Sửa lỗi trong bộ test Batch 0 (test BE thiếu manager_id, FE dùng render không await)
description: Sửa 2 lỗi trong test do QA viết ở Task 1.S — BE thiếu manager_id khi tạo employee, FE dùng render() không await và monkey-patch jest.setup.js
status: COMPLETE
started: 2026-07-27
completed: 2026-07-27
skills_used:
  - pytest-asyncio
  - jwt-decode-python
  - rntl-v14-async-render
  - typescript-type-narrowing
---

## Progress

- [x] Read state file và fill description
- [x] Sửa lỗi #1 BE: 2 test thiếu manager_id — thêm cả manager lẫn employee (phủ cả 2 vai)
- [x] Sửa lỗi #2 FE: xóa patchRNTLRenderSync khỏi jest.setup.js (182→87 dòng)
- [x] Sửa ErrorBoundary.test.tsx — tất cả it() thành async + await render()
- [x] Sửa chat-error.test.tsx — renderChat() thành async + await khắp nơi
- [x] Thêm "types": ["jest"] vào tsconfig.json để tsc nhận globals
- [x] Sửa typing bug trong crashReporter.test.ts (makeCrash dùng Partial<CrashPayload>)
- [x] Phát hiện và báo cáo dev bug: crashReporter.ts:117 global.fetch kiểu sai
- [x] Fix dev bug TS: cast global.fetch as unknown as typeof fetch
- [x] Chạy kiểm chứng tất cả 4 lệnh tiêu chí

## Files Modified

| File | Action | Notes |
|------|--------|-------|
| `backend/tests/test_crash_logs_api.py` | Sửa | 2 test: thêm manager+employee với JWT decode để lấy manager_id |
| `frontend/jest.setup.js` | Sửa | Xóa patchRNTLRenderSync (182→87 dòng) |
| `frontend/__tests__/ErrorBoundary.test.tsx` | Sửa | Tất cả it() → async, thêm await render() |
| `frontend/__tests__/chat-error.test.tsx` | Sửa | renderChat() → async, tất cả renderChat() → await renderChat() |
| `frontend/__tests__/crashReporter.test.ts` | Sửa | makeCrash() dùng Partial<CrashPayload> + return CrashPayload |
| `frontend/tsconfig.json` | Sửa | Thêm "types": ["jest"] |
| `frontend/src/errors/crashReporter.ts` | Sửa | global.fetch cast as unknown as typeof fetch |

## Completion Notes

### Lỗi #1 — Backend
Chọn cách phủ CẢ HAI vai (manager + employee):
- Tạo manager trước (không cần manager_id)
- Decode JWT của manager để lấy UUID → dùng làm manager_id cho employee
- Mỗi test assert 403 cho cả hai roles riêng biệt
- Lỗi padding operator: `'=' * (4-n%4) % 4` → `'=' * ((4-n%4) % 4)`

### Lỗi #2 — Frontend  
- jest.setup.js: xóa hoàn toàn IIFE patchRNTLRenderSync (dòng 89–181 cũ)
- ErrorBoundary.test.tsx: 6 test cases tất cả thành async + await render()
- Test "không throw" đổi từ expect(fn).not.toThrow() sang await render() trực tiếp (clean hơn với async)
- chat-error.test.tsx: renderChat() → async function, 8 chỗ gọi đều thêm await
- Test "không sập" đổi từ expect(()=>{ renderChat() }).not.toThrow() sang await renderChat()

### Bug phát hiện thêm (không trong yêu cầu ban đầu)
1. tsconfig.json thiếu "types": ["jest"] → jest globals (describe/it/expect) không typed
2. crashReporter.test.ts: makeCrash() typed quá rộng (source: string thay vì CrashSource)
3. src/errors/crashReporter.ts:117: global.fetch bị TypeScript infer kiểu từ jest.setup.js mock (0-parameter) — dev cần biết cast as unknown as typeof fetch

### Kết quả 4 lệnh tiêu chí
```
BE crash_logs: 14/14 XANH
BE full suite: 812 pass, 5 fail (test_crash_middleware.py — out of scope, song song agent khác)
FE jest --ci: crashReporter 30/30 XANH, redact XANH, ErrorBoundary XANH; chat-error 2/9 XANH 7/9 ĐỎ (đúng lý do: thiếu code Task 1.4, không phải cấu hình)
FE tsc --noEmit: 0 lỗi
```
