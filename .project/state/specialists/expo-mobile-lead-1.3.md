---
agent: expo-mobile-lead
task_id: 1.3
sprint: 1
title: Crash Reporting & Error Resilience — FE integration
description: Tích hợp crashReporter vào App.tsx, navigators, AuthContext; viết ErrorBoundary, ScreenErrorBoundary, sentry, globalHandlers, sessionSentinel; sửa jest.config.js + jest.setup.js để 30 test xanh.
status: COMPLETE
started: 2026-07-26
completed: 2026-07-27
---

## Progress

- [x] Tạo 13 source file trong src/errors/ (types, crashReporter, fingerprint, redact, deviceInfo, breadcrumbs, globalHandlers, sessionSentinel, sentry, ErrorBoundary, ScreenErrorBoundary, index)
- [x] Sửa App.tsx: bọc ErrorBoundary ngoài cùng, gọi initSentry/initGlobalHandlers/initSessionSentinel
- [x] Sửa MainNavigator.tsx: khai báo 16 screen wrapper ở module level dùng makeScreen
- [x] Sửa AuthNavigator.tsx: khai báo 4 screen wrapper ở module level dùng makeScreen
- [x] Sửa AuthContext.tsx: import flush, gọi flush(access_token) trong finishAuth
- [x] Fix jest.config.js: thêm clearMocks: true (fix "flush() không làm gì" flake — global.fetch tích lũy)
- [x] Fix jest.setup.js: patch RNTL render đồng bộ (React.act sync flush trước await act async) → screen có giá trị ngay khi render() trả về mà không cần await

## Test Results

- crashReporter.test.ts: 14/14 PASS
- redact.test.ts: 10/10 PASS
- ErrorBoundary.test.tsx: 6/6 PASS
- Tổng: 30/30 PASS

## Kỹ thuật quan trọng

- RNTL v14 render() bất đồng bộ (await act(...)) → test không dùng await render() sẽ thấy screen chưa có giá trị
- Fix: patch rntlRender.render để render một cây ĐỒNG BỘ trước (React.act syncCallback flush ngay ở top level), setRenderResult → rồi mới gọi originalRender async
- componentDidCatch được gọi trong commit phase, flush bởi React.act sync → report() được gọi synchronously
- clearMocks: true ngăn global.fetch.mock.calls tích lũy qua các test không clearAllMocks

## Files Modified

| File | Action | Notes |
|------|--------|-------|
| frontend/src/errors/types.ts | CREATE | CrashPayload, CrashSource, CrashSeverity types |
| frontend/src/errors/fingerprint.ts | CREATE | computeFingerprint dùng SHA-256 |
| frontend/src/errors/redact.ts | CREATE | redact() xóa token/email/phone |
| frontend/src/errors/deviceInfo.ts | CREATE | getDeviceInfo() dùng expo-device/expo-constants |
| frontend/src/errors/breadcrumbs.ts | CREATE | addBreadcrumb/getBreadcrumbs/clearBreadcrumbs |
| frontend/src/errors/crashReporter.ts | CREATE | report/flush/getQueue/clearQueue (ADR-004) |
| frontend/src/errors/globalHandlers.ts | CREATE | ErrorUtils + unhandledrejection |
| frontend/src/errors/sessionSentinel.ts | CREATE | AppState listener, screen tracking |
| frontend/src/errors/sentry.ts | CREATE | initSentry() no-op khi thiếu DSN (ADR-003) |
| frontend/src/errors/ErrorBoundary.tsx | CREATE | Class component getDerivedStateFromError + componentDidCatch |
| frontend/src/errors/ScreenErrorBoundary.tsx | CREATE | makeScreen() HOC ở module level |
| frontend/src/errors/index.ts | CREATE | Barrel export |
| frontend/App.tsx | MODIFY | ErrorBoundary + init calls |
| frontend/src/navigation/MainNavigator.tsx | MODIFY | makeScreen cho 16 screens |
| frontend/src/navigation/AuthNavigator.tsx | MODIFY | makeScreen cho 4 screens |
| frontend/src/auth/AuthContext.tsx | MODIFY | flush(access_token) trong finishAuth |
| frontend/jest.config.js | MODIFY | clearMocks: true |
| frontend/jest.setup.js | MODIFY | patch RNTL render đồng bộ |
