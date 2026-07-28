---
agent: vfm-agent-company:google-qa-engineer
task_id: 1.S
sprint: 1
title: BDD scenarios + dựng nền jest-expo
description: Viết BDD scenarios Gherkin tiếng Việt, dựng jest-expo test framework, tạo skeleton test đỏ cho sprint Crash Reporting
status: COMPLETE
started: 2026-07-27
completed: 2026-07-27
skills_used: [vfm-agent-company:qa-testing]
---

## Progress

- [x] Read state file and filled `description:` field above
- [x] Read sprint-1.md, architecture.md, conftest.py, test example, package.json
- [x] Viết 3 file .feature (BDD Gherkin tiếng Việt)
- [x] Tạo jest.config.js + jest.setup.js
- [x] Cập nhật frontend/package.json (devDeps + script test)
- [x] Cài devDependencies FE bằng npx expo install --dev
- [x] Viết skeleton test FE (4 file __tests__)
- [x] Viết skeleton test BE (2 file tests/)
- [x] Chạy npx jest --ci — cấu hình OK, test đỏ vì thiếu code
- [x] Chạy pytest tests/ -v — 794 old tests PASS, 23 new tests ĐỎ (thiếu code)

## Files Modified

| File | Action | Notes |
|------|--------|-------|
| .project/scenarios/sprint-1/crash-logging.feature | CREATE | BDD scenarios cho Task 1.1+1.2 |
| .project/scenarios/sprint-1/error-boundary.feature | CREATE | BDD scenarios cho Task 1.3 |
| .project/scenarios/sprint-1/chat-error-handling.feature | CREATE | BDD scenarios cho Task 1.4 |
| frontend/jest.config.js | CREATE | jest-expo preset + transformIgnorePatterns |
| frontend/jest.setup.js | CREATE | mock AsyncStorage, expo-device, expo-constants, fetch |
| frontend/package.json | EDIT | thêm devDeps + script test |
| frontend/__tests__/crashReporter.test.ts | CREATE | skeleton đỏ |
| frontend/__tests__/redact.test.ts | CREATE | skeleton đỏ |
| frontend/__tests__/ErrorBoundary.test.tsx | CREATE | skeleton đỏ |
| frontend/__tests__/chat-error.test.tsx | CREATE | skeleton đỏ |
| backend/tests/test_crash_logs_api.py | CREATE | skeleton đỏ |
| backend/tests/test_crash_middleware.py | CREATE | skeleton đỏ |

## Completion Notes

### Kết quả chạy test thực tế

**FE — npx jest --ci** (4 test suites, đỏ vì THIẾU CODE):
- 4/4 suites: "Test suite failed to run" với lỗi "Cannot find module"
- Nguyên nhân: src/errors/crashReporter.ts, src/errors/redact.ts, src/errors/ErrorBoundary.tsx chưa tồn tại (dev tạo ở Batch 1)
- Đây là "đỏ vì thiếu code", KHÔNG phải "đỏ vì cấu hình" — transform OK, preset OK, không có SyntaxError

**BE — pytest tests/ -v** (823 tests):
- 794 PASS (bộ test cũ xanh, không regression)
- 4 SKIP (pre-existing)
- 23 FAIL (test mới đỏ vì thiếu code: CrashLog model, crash_logs router, CrashCaptureMiddleware chưa tồn tại)
- Thời gian: 206.48s

### Quyết định kỹ thuật
- Cài `react-test-renderer@19.2.3` thay vì 19.2.8 vì react trong repo là 19.2.3 (tránh peer dep conflict)
- jest.mock với factory vẫn fail "Cannot find module" trong jest-expo — đây là hành vi bình thường vì jest-expo validate path trước khi dùng factory. Cần `{virtual: true}` hoặc stub file nếu muốn test chạy ở tầng individual (dev quyết định ở Batch 1)
- BE skeleton test import `from app.models import CrashLog` bên trong hàm test (không ở module level) → test được collect thành công, chỉ fail khi run
- Rate limit test (test_post_crash_logs_rate_limit_429) cần Redis thật — conftest monkeypatch FakeSnapshotStore nhưng Redis rate-limit counter cần xem xét khi implement
