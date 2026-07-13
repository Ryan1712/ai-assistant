# Plan 7 â€” Push notification, Email theo ma tráº­n, Voice note, Queue UI

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Checkbox (`- [ ]`) Ä‘á»ƒ tracking.

**Goal:** HoÃ n thiá»‡n 4 khoáº£ng trá»‘ng cÃ²n láº¡i cá»§a funtional-plan: push notification tháº­t (Expo Push), email theo ma tráº­n tÆ°Æ¡ng tÃ¡c, ghi Ã¢m/voice note (transcription stub), vÃ  UI hÃ ng Ä‘á»£i (há»§y/Æ°u tiÃªn) trÃªn FE.

**Architecture:** Má»i tÃ­ch há»£p ngoÃ i (Expo Push, SMTP, STT) Ä‘á»u Ä‘á»©ng sau client protocol + mock máº·c Ä‘á»‹nh qua config â€” pattern nhÆ° portal_service. Notification táº­p trung vá» helper `notify()` (ghi báº£ng + báº¯n push best-effort, khÃ´ng bao giá» raise). Email/voice lÃ  model má»›i cÃ³ `workspace_id`, quyá»n á»Ÿ service layer.

**Tech Stack:** BE nhÆ° cÅ© (+`python-multipart` cho upload). FE: expo-notifications, expo-audio.

## Global Constraints (CLAUDE.md)
- workspace_id má»i báº£ng; quyá»n á»Ÿ service layer; actor tá»« JWT; TDD, má»—i task 1 commit; export openapi khi Ä‘á»•i contract.

## Quyáº¿t Ä‘á»‹nh thiáº¿t káº¿
- **Push:** `devices.push_token` (nullable). `PUT /api/v1/devices/push-token` (actor tá»± Ä‘Äƒng kÃ½ cho device_uuid cá»§a mÃ¬nh). `push_service.PushClient`: `MockPushClient` (default, `push_mock=True`) / `ExpoPushClient` (POST exp.host/--/api/v2/push/send). `notify()` helper thay 4 chá»— `db.add(Notification(...))` hiá»‡n cÃ³ (assign_task, task_update, account_locked, unlock_request) â€” push best-effort trÆ°á»›c commit, nuá»‘t lá»—i.
- **Email:** ma tráº­n: employee â‡Ž employee; cÃ²n láº¡i tá»± do (trong workspace). Model `EmailMessage(sender_id, recipient_id, subject, body)`. Tool `send_email` **sensitive** (tÃ¡i dÃ¹ng flow xÃ¡c nháº­n 2 bÆ°á»›c sáºµn cÃ³). `EmailClient`: Mock default (`email_mock=True`); real client CHÆ¯A implement â€” chá» product chá»‘t OAuth send-as hay SMTP (phá»¥ lá»¥c funtional-plan). REST: `GET /api/v1/emails?box=inbox|sent`.
- **Voice note:** model `VoiceNote(author_id, file_path, transcript, language, tags, task_id?, project_id?)` â€” cÃ¡ nhÃ¢n nhÆ° Note. `POST /api/v1/voice-notes` (multipart) lÆ°u file vÃ o `storage_dir/voice/{workspace_id}/`, transcription qua `TranscriptionClient` (Mock default `stt_mock=True`, tráº£ transcript rá»—ng + language "und"; real STT chá» chá»n provider). GET list (filter tag/ngÃ y) + GET file. Tools: `list_voice_notes`, `get_voice_note` (Ä‘á»c transcript Ä‘á»ƒ AI biáº¿n thÃ nh task qua tool sáºµn cÃ³).
- **Queue UI (FE):** danh sÃ¡ch request queued trong mÃ n chat: nÃºt Há»§y (`POST /chat-requests/{id}/cancel`), nÃºt Æ¯u tiÃªn (`POST /chat-requests/{id}/reorder` body `{before_id: null}` = lÃªn Ä‘áº§u). FE Ä‘Äƒng kÃ½ push token khi Ä‘Äƒng nháº­p (guarded â€” Expo Go khÃ´ng há»— trá»£ remote push, chá»‰ log). Ghi Ã¢m má»™t cháº¡m á»Ÿ tab HÃ´m nay â†’ upload voice note.

### Task 1: Push â€” token + client + notify()
- [x] `devices.push_token` String(128) nullable; `PUT /api/v1/devices/push-token` {device_uuid, push_token} (chá»‰ device cá»§a chÃ­nh actor, 404 náº¿u khÃ´ng cÃ³); `app/services/push_service.py` (MockPushClient ghi láº¡i `sent`, ExpoPushClient httpx, `get_push_client()` theo `settings.push_mock=True`); `app/services/notify.py::notify(db, *, workspace_id, recipient_id, type, payload)` â€” add Notification + push tá»›i má»i push_token cá»§a recipient, try/except nuá»‘t lá»—i; thay 4 call-site. Test: Ä‘Äƒng kÃ½ token; assign task â†’ MockPushClient nháº­n Ä‘Ãºng recipient/type; lá»—i push khÃ´ng phÃ¡ transaction. Commit `feat(be): expo push token + notify fanout`.

### Task 2: Email theo ma tráº­n
- [x] Model `EmailMessage`; `app/services/email_service.py::send_email(db, actor, recipient_id, subject, body)` â€” cÃ¹ng workspace (404), ma tráº­n employeeâ‡Žemployee (403 `interaction_not_allowed`), ghi row + `EmailClient.send` (mock); `list_emails(db, actor, box)`. Tool `send_email` sensitive. REST `GET /api/v1/emails`. Test: employeeâ†’employee 403; employeeâ†’ceo OK; managerâ†’manager OK; tool náº±m trong SENSITIVE_TOOLS; inbox/sent Ä‘Ãºng. Commit `feat(be): role-matrix email (mock client) + send_email tool`.

### Task 3: Voice note
- [x] `python-multipart` vÃ o requirements. Model `VoiceNote`; `app/services/voice_service.py`: `create_voice_note(db, actor, filename, data, tags, task_id, project_id)` (lÆ°u file an toÃ n â€” uuid filename, Ä‘Ãºng workspace dir; transcription mock; link task/project pháº£i visible), `list_voice_notes(db, actor, tag?, on_date?)` (author-only), `get_file(db, actor, id)`. REST: POST multipart, GET list, GET `/{id}/file` (FileResponse). Tools `list_voice_notes`, `get_voice_note`. Test: upload â†’ file tá»“n táº¡i Ä‘Ãºng thÆ° má»¥c workspace + transcript mock; author-only; path khÃ´ng traversal (uuid filename). Commit `feat(be): voice note upload + transcription stub + tools`.

### Task 4: Migration + openapi
- [x] Migration tay: `devices.push_token`, `email_messages`, `voice_notes`. Full pytest. Export openapi. Commit `chore(be): plan7 migration + openapi refresh`.

### Task 5: FE queue UI + push Ä‘Äƒng kÃ½ + ghi Ã¢m
- [x] `src/api/chat.ts` thÃªm `reorderRequest`; mÃ n chat: khá»‘i "HÃ ng Ä‘á»£i" liá»‡t kÃª queued (ná»™i dung rÃºt gá»n + nÃºt âœ• há»§y + nÃºt â¬† Æ°u tiÃªn).
- [x] `expo-notifications`: sau Ä‘Äƒng nháº­p, xin quyá»n + `getExpoPushTokenAsync` (try/catch â€” Expo Go bá» qua), `PUT /devices/push-token`.
- [x] `expo-audio`: nÃºt "ðŸŽ™ï¸ Ghi Ã¢m nhanh" á»Ÿ tab HÃ´m nay (báº¥m ghi/báº¥m dá»«ng â†’ upload `POST /voice-notes`), hiá»‡n danh sÃ¡ch ghi Ã¢m hÃ´m nay. Typecheck + expo export. Commit `feat(fe): queue controls + push token + quick voice note`.

## Ghi chÃº chá» product
- Email real (OAuth send-as vs SMTP) vÃ  STT provider (nháº­n diá»‡n ngÃ´n ngá»¯) chÆ°a chá»‘t â€” mock sáºµn interface.
