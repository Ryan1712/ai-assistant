# Plan 7 — Push notification, Email theo ma trận, Voice note, Queue UI

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Checkbox (`- [ ]`) để tracking.

**Goal:** Hoàn thiện 4 khoảng trống còn lại của funtional-plan: push notification thật (Expo Push), email theo ma trận tương tác, ghi âm/voice note (transcription stub), và UI hàng đợi (hủy/ưu tiên) trên FE.

**Architecture:** Mọi tích hợp ngoài (Expo Push, SMTP, STT) đều đứng sau client protocol + mock mặc định qua config — pattern như portal_service. Notification tập trung về helper `notify()` (ghi bảng + bắn push best-effort, không bao giờ raise). Email/voice là model mới có `workspace_id`, quyền ở service layer.

**Tech Stack:** BE như cũ (+`python-multipart` cho upload). FE: expo-notifications, expo-audio.

## Global Constraints (CLAUDE.md)
- workspace_id mọi bảng; quyền ở service layer; actor từ JWT; TDD, mỗi task 1 commit; export openapi khi đổi contract.

## Quyết định thiết kế
- **Push:** `devices.push_token` (nullable). `PUT /api/v1/devices/push-token` (actor tự đăng ký cho device_uuid của mình). `push_service.PushClient`: `MockPushClient` (default, `push_mock=True`) / `ExpoPushClient` (POST exp.host/--/api/v2/push/send). `notify()` helper thay 4 chỗ `db.add(Notification(...))` hiện có (assign_task, task_update, account_locked, unlock_request) — push best-effort trước commit, nuốt lỗi.
- **Email:** ma trận: employee ⇎ employee; còn lại tự do (trong workspace). Model `EmailMessage(sender_id, recipient_id, subject, body)`. Tool `send_email` **sensitive** (tái dùng flow xác nhận 2 bước sẵn có). `EmailClient`: Mock default (`email_mock=True`); real client CHƯA implement — chờ product chốt OAuth send-as hay SMTP (phụ lục funtional-plan). REST: `GET /api/v1/emails?box=inbox|sent`.
- **Voice note:** model `VoiceNote(author_id, file_path, transcript, language, tags, task_id?, project_id?)` — cá nhân như Note. `POST /api/v1/voice-notes` (multipart) lưu file vào `storage_dir/voice/{workspace_id}/`, transcription qua `TranscriptionClient` (Mock default `stt_mock=True`, trả transcript rỗng + language "und"; real STT chờ chọn provider). GET list (filter tag/ngày) + GET file. Tools: `list_voice_notes`, `get_voice_note` (đọc transcript để AI biến thành task qua tool sẵn có).
- **Queue UI (FE):** danh sách request queued trong màn chat: nút Hủy (`POST /chat-requests/{id}/cancel`), nút Ưu tiên (`POST /chat-requests/{id}/reorder` body `{before_id: null}` = lên đầu). FE đăng ký push token khi đăng nhập (guarded — Expo Go không hỗ trợ remote push, chỉ log). Ghi âm một chạm ở tab Hôm nay → upload voice note.

### Task 1: Push — token + client + notify()
- [ ] `devices.push_token` String(128) nullable; `PUT /api/v1/devices/push-token` {device_uuid, push_token} (chỉ device của chính actor, 404 nếu không có); `app/services/push_service.py` (MockPushClient ghi lại `sent`, ExpoPushClient httpx, `get_push_client()` theo `settings.push_mock=True`); `app/services/notify.py::notify(db, *, workspace_id, recipient_id, type, payload)` — add Notification + push tới mọi push_token của recipient, try/except nuốt lỗi; thay 4 call-site. Test: đăng ký token; assign task → MockPushClient nhận đúng recipient/type; lỗi push không phá transaction. Commit `feat(be): expo push token + notify fanout`.

### Task 2: Email theo ma trận
- [ ] Model `EmailMessage`; `app/services/email_service.py::send_email(db, actor, recipient_id, subject, body)` — cùng workspace (404), ma trận employee⇎employee (403 `interaction_not_allowed`), ghi row + `EmailClient.send` (mock); `list_emails(db, actor, box)`. Tool `send_email` sensitive. REST `GET /api/v1/emails`. Test: employee→employee 403; employee→ceo OK; manager→manager OK; tool nằm trong SENSITIVE_TOOLS; inbox/sent đúng. Commit `feat(be): role-matrix email (mock client) + send_email tool`.

### Task 3: Voice note
- [ ] `python-multipart` vào requirements. Model `VoiceNote`; `app/services/voice_service.py`: `create_voice_note(db, actor, filename, data, tags, task_id, project_id)` (lưu file an toàn — uuid filename, đúng workspace dir; transcription mock; link task/project phải visible), `list_voice_notes(db, actor, tag?, on_date?)` (author-only), `get_file(db, actor, id)`. REST: POST multipart, GET list, GET `/{id}/file` (FileResponse). Tools `list_voice_notes`, `get_voice_note`. Test: upload → file tồn tại đúng thư mục workspace + transcript mock; author-only; path không traversal (uuid filename). Commit `feat(be): voice note upload + transcription stub + tools`.

### Task 4: Migration + openapi
- [ ] Migration tay: `devices.push_token`, `email_messages`, `voice_notes`. Full pytest. Export openapi. Commit `chore(be): plan7 migration + openapi refresh`.

### Task 5: FE queue UI + push đăng ký + ghi âm
- [ ] `src/api/chat.ts` thêm `reorderRequest`; màn chat: khối "Hàng đợi" liệt kê queued (nội dung rút gọn + nút ✕ hủy + nút ⬆ ưu tiên).
- [ ] `expo-notifications`: sau đăng nhập, xin quyền + `getExpoPushTokenAsync` (try/catch — Expo Go bỏ qua), `PUT /devices/push-token`.
- [ ] `expo-audio`: nút "🎙️ Ghi âm nhanh" ở tab Hôm nay (bấm ghi/bấm dừng → upload `POST /voice-notes`), hiện danh sách ghi âm hôm nay. Typecheck + expo export. Commit `feat(fe): queue controls + push token + quick voice note`.

## Ghi chú chờ product
- Email real (OAuth send-as vs SMTP) và STT provider (nhận diện ngôn ngữ) chưa chốt — mock sẵn interface.
