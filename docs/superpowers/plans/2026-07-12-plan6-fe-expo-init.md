# Plan 6 — FE Expo khởi tạo (auth + chat streaming + dashboard)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Dựng app mobile Expo (React Native + TypeScript) trong `frontend/`, nối được backend hiện có: đăng nhập/đăng ký (workspace + mã mời), màn Chat với hàng đợi + streaming qua WebSocket, màn Dashboard "Hôm nay".

**Architecture:** Expo + expo-router (file-based routing), TypeScript. Client API mỏng bọc `fetch` với base URL từ `EXPO_PUBLIC_API_URL`; access/refresh token lưu `expo-secure-store` (fallback AsyncStorage trên web); AuthContext cung cấp user + token, tự refresh khi 401. Chat: POST tạo chat-request → nhận stream qua WS `/api/v1/ws/conversations/{id}` (token qua query param), render token tăng dần. Không dùng state-management ngoài (YAGNI) — React context + hooks.

**Tech Stack:** Expo SDK (mới nhất), expo-router, TypeScript, expo-secure-store.

## Global Constraints
- Contract API lấy từ `openapi.json` ở repo root — không tự bịa endpoint.
- Danh tính từ JWT; FE không bao giờ gửi user_id tự khai cho hành động của chính mình.
- Text UI tiếng Việt (sản phẩm cho user Việt).
- FE không gọi LLM trực tiếp — mọi thứ qua backend.

### Task 1: Scaffold
- [ ] `npx create-expo-app@latest frontend --template blank-typescript`; thêm expo-router, expo-secure-store; cấu trúc `app/` (routes), `src/api/`, `src/auth/`; chạy được `npx expo start`. Commit `feat(fe): scaffold expo app`.

### Task 2: API client + auth
- [ ] `src/api/client.ts`: `apiFetch(path, opts)` gắn Bearer, auto-refresh 401 (POST /auth/refresh, retry 1 lần), base = `EXPO_PUBLIC_API_URL` (default `http://localhost:8000`).
- [ ] `src/auth/AuthContext.tsx`: `signInLogin`, `signInSignupWorkspace`, `signInSignupCode`, `signOut`, lưu token SecureStore, khôi phục phiên khi mở app.
- [ ] Màn `app/(auth)/login.tsx`, `app/(auth)/signup-workspace.tsx`, `app/(auth)/signup-code.tsx`; redirect vào `(main)` khi có phiên. Commit `feat(fe): auth flow`.

### Task 3: Chat streaming
- [ ] `src/api/chat.ts`: tạo/list conversations, POST chat-requests, list messages.
- [ ] `src/api/ws.ts`: kết nối WS conversation, parse event (`token`, `status_update`, `request_done`, `request_failed`, `confirmation_required`).
- [ ] `app/(main)/chat.tsx`: khung chat, gửi không chờ (hàng đợi), hiện "đang xử lý m/n", streaming text, nút xác nhận/từ chối khi `confirmation_required`, nút hủy request. Commit `feat(fe): chat screen with queue + streaming`.

### Task 4: Dashboard Hôm nay + đổi gói
- [ ] `app/(main)/index.tsx` (tab Hôm nay): GET /dashboard/today — due_today/overdue/in_progress, recent_updates, notes_today, counters; kéo-refresh.
- [ ] Hiện gói (GET /subscription) + mã mời (CEO). Commit `feat(fe): today dashboard`.

## Ghi chú
- Push notification (Expo push token) + voice: plan sau, cần build dev client.
- FE dev chính thức có thể tiếp quản — code này là skeleton chạy được end-to-end.
