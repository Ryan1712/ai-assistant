# Voice input cho chat + đính kèm audio + xóa task/project — Design

Ngày: 2026-07-19. Bối cảnh: app chốt **chỉ dùng trên iPhone** (CEO dùng điện thoại), DEV chính build iOS qua EAS (native module không còn là trở ngại). Web (`expo start --web`) chỉ là môi trường dev/test.

## Quyết định sản phẩm (đã chốt với user trong phiên 2026-07-19)

1. **Nói ngắn (≤1 phút) → text bằng speech-to-text CỦA iOS** (SFSpeechRecognizer, on-device/Apple server, miễn phí) — không dùng STT server cho luồng này. Lý do: lệnh chat ngắn, giới hạn ~1 phút của iOS dictation không thành vấn đề.
2. **Input dài (meeting 10-15 phút) → user NÉM FILE AUDIO vào chat** làm input. Không ghi âm dài trực tiếp trong chat.
3. AI (Claude) **không nghe được audio** — file dài chỉ thành input thật sự cho AI khi có STT server-side (Whisper…). **Chưa chọn provider** → phần "AI đọc nội dung file" nằm NGOÀI scope; thiết kế phải sẵn chỗ để cắm vào sau (pipeline transcribe async + `transcript_status` đã có sẵn từ trước).
4. Xóa task/project là gap cơ bản (hiện chỉ có create/patch) — làm luôn đợt này.

## Feature 1 — Mic dictation trong màn chat

**Thư viện:** `expo-speech-recognition` (config plugin, iOS SFSpeechRecognizer + Web Speech API fallback). Cần dev build cho iOS (DEV chính lo); trên web Chrome chạy được để dev tự test; môi trường không hỗ trợ (Expo Go, Safari web cũ) thì **ẩn nút mic** (feature-detect, lazy import — giống pattern guard push notification hiện có).

**UX:** nút 🎙️ cạnh ô nhập chat. Bấm → bắt đầu nhận dạng (locale mặc định `vi-VN`, interim results đổ trực tiếp vào ô nhập theo thời gian thực) → bấm lại để dừng → text nằm trong ô nhập, sửa được, gửi như tin nhắn thường. Đang nhận dạng thì nút đổi trạng thái (màu đỏ/pulse).

**Ngoài scope:** chọn ngôn ngữ (hardcode vi-VN), tự nhận diện ngôn ngữ (iOS không hỗ trợ cho dictation).

**Lỗi:** không được cấp quyền mic/speech → message thân thiện; lỗi giữa chừng → giữ nguyên text đã nhận được.

## Feature 2 — Đính kèm file audio vào chat

**UX:** nút 📎 cạnh ô nhập → `expo-document-picker` lọc `audio/*` → chip trên ô nhập (tên file) + caption tùy chọn trong ô nhập → bấm gửi. Trong lịch sử chat, tin nhắn hiện **bubble audio phát lại được** (dùng lại `voiceNoteAudioSource` + player như thư viện) + caption.

**Luồng dữ liệu:**
- FE upload file qua `POST /api/v1/voice-notes` sẵn có (→ file tự nằm trong thư viện ghi âm = tính năng "lưu audio dùng sau") lấy `voice_note_id`, rồi `POST .../messages` với body `{content, voice_note_id}`.
- BE: `MessageSendIn.voice_note_id: uuid | None`. `send_message` validate voice note thuộc đúng actor (author-only, cùng workspace — tái dùng `_get_own_or_404` của voice_service) rồi lưu vào cột mới `ChatRequest.voice_note_id` và `Message.voice_note_id` (cả 2 nullable FK, 1 migration). Content của Message = caption (hoặc mặc định `"[Đã gửi 1 file ghi âm]"` nếu caption rỗng) + dòng text `"[Đính kèm ghi âm: <title hoặc thời lượng>]"` để model biết có file.
- Worker (`run_agent_loop` hoặc bước trước nó): nếu request có `voice_note_id` và STT thật được bật (`stt_mock=False`) và transcript chưa done → **transcribe inline trước khi chạy agent** (tái dùng `transcribe_note`), sau đó **append transcript vào content của user Message trong DB** (thêm 1 text block `"[Transcript ghi âm]:\n..."`) — nhờ đó mọi lượt sau của conversation đều thấy transcript qua `_load_history`, không cần cơ chế riêng. Khi `stt_mock=True` (hiện tại): bỏ qua bước này — model chỉ thấy dòng "[Đính kèm ghi âm...]" và sẽ trả lời trung thực là chưa đọc được nội dung.
- `MessageOut` thêm `voice_note_id` để FE render bubble audio khi reload. `_load_history` không đổi (content thuần text block, an toàn với Anthropic API).

**Giới hạn hiển thị:** transcript dài không render toàn bộ trong bubble — FE cắt hiển thị (line clamp), bubble chủ đạo là audio + caption.

## Feature 3 — Xóa task / project

**Quyền (theo service layer, nhất quán mô hình hiện có):**
- `delete_task`: ai có quyền sửa task đó (cùng điều kiện với `update_task` hiện tại) thì xóa được.
- `delete_project`: chỉ CEO hoặc owner của project.

**Cascade:** xóa task → xóa các row con (assignees, updates, comments, attachments — file attachment trên đĩa unlink best-effort như voice note). Voice note/email đang tham chiếu `task_id`/`project_id` → set NULL (cột vốn nullable). Xóa project → xóa toàn bộ task của nó (cùng cascade trên). Không soft-delete.

**Bề mặt:**
- Service: `work_service.delete_task` / `delete_project` (hoặc file service tương ứng hiện có).
- REST: `DELETE /api/v1/tasks/{id}`, `DELETE /api/v1/projects/{id}` → 204.
- Agent tools: `delete_task`, `delete_project` — **đăng ký vào `SENSITIVE_TOOLS`** → đi qua confirm card sẵn có (CEO duyệt trước khi xóa, đúng triết lý chat-first).
- FE: màn task detail thêm nút "🗑 Xóa task" (2 chạm xác nhận như thư viện ghi âm), chỉ hiện khi user có quyền (gọi cứ API, lỗi thì hiện message — không tự validate quyền ở FE, theo pattern Team screen). Xóa project qua chat là chính, FE không làm màn riêng đợt này.

## Data model / contract

- Migration mới: `chat_requests.voice_note_id` (nullable FK → voice_notes, `ondelete=SET NULL`), `messages.voice_note_id` (như trên).
- `MessageSendIn` + `ChatRequestOut` + `MessageOut` thêm `voice_note_id`.
- 2 route DELETE mới + 2 tool mới → chạy lại `export_openapi.py`.

## Testing

- BE: TDD như thường — validate voice_note_id sai chủ → 422/404; message content có dòng đính kèm; worker append transcript khi stt thật (test bằng monkeypatch client giả); delete task/project đúng quyền + cascade + 404 cross-workspace; tool nhạy cảm vào confirm flow.
- FE: `tsc --noEmit` + smoke Playwright trên web (mic chỉ test feature-detect ẩn/hiện; dictation thật test tay trên iOS build của DEV).

## Ngoài scope đợt này

- STT provider thật (chờ chọn/cấp key — khi có chỉ đổi config + implement 1 client).
- AI tự đọc file dài khi chưa có STT.
- Language picker cho dictation; xóa project từ FE; soft-delete/undo.
