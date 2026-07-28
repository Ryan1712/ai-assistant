# language: vi
# Tính năng này map về Task 1.1 (endpoint crash-logs) + Task 1.2 (CrashCaptureMiddleware)
# Tiêu chí nghiệm thu: sprint-1.md § Task 1.1 và § Task 1.2

Tính năng: Ghi nhận crash log từ client và unhandled exception phía server

  Bối cảnh:
    Giả sử hệ thống đang chạy với bảng crash_logs đã được migration
    Và có workspace A với CEO là "ceo@a.vn"
    Và có workspace B với CEO là "ceo@b.vn" và user thường là "nv@b.vn"
    Và CEO workspace A đã đăng nhập và có JWT hợp lệ

  # ─── Batch Ingest ───────────────────────────────────────────────────────────

  Kịch bản: Gửi batch crash log hợp lệ và server chấp nhận
    Giả sử client gửi POST /api/v1/crash-logs với danh sách 3 bản ghi hợp lệ
    Khi server xử lý request
    Thì server trả về HTTP 200
    Và body chứa {"accepted": 3, "duplicates": 0}
    Và 3 bản ghi được lưu vào bảng crash_logs với workspace_id lấy từ JWT

  Kịch bản: workspace_id và user_id trong bản ghi lấy từ JWT, không từ body
    Giả sử client gửi POST /api/v1/crash-logs với body có chứa workspace_id giả mạo
    Khi server xử lý request
    Thì server bỏ qua workspace_id trong body
    Và lưu bản ghi với workspace_id = workspace của token hiện tại

  Kịch bản: Gửi batch vượt quá 20 bản ghi
    Giả sử client gửi POST /api/v1/crash-logs với danh sách 21 bản ghi
    Khi server xử lý request
    Thì server trả về HTTP 422 (validation error)

  # ─── Dedupe theo client_event_id ─────────────────────────────────────────

  Kịch bản: Gửi lại cùng client_event_id không tạo bản ghi trùng
    Giả sử client đã gửi một crash log có client_event_id = "uuid-abc-123"
    Khi client gửi lại cùng crash log đó (retry hàng đợi)
    Thì server trả về HTTP 200
    Và body chứa {"accepted": 0, "duplicates": 1}
    Và bảng crash_logs vẫn chỉ có 1 bản ghi với client_event_id đó

  Kịch bản: client_event_id của workspace A không xung đột với workspace B
    Giả sử workspace A đã có bản ghi với client_event_id = "uuid-xyz"
    Khi workspace B gửi crash log có client_event_id = "uuid-xyz"
    Thì bản ghi của workspace B được chấp nhận (không coi là trùng)

  # ─── Cắt payload quá dài ─────────────────────────────────────────────────

  Kịch bản: message vượt 2000 ký tự bị cắt phía server
    Giả sử client gửi crash log với message dài 5000 ký tự
    Khi server lưu bản ghi
    Thì bản ghi trong DB có message chỉ dài 2000 ký tự (bị cắt)
    Và server KHÔNG trả về 500

  Kịch bản: stack trace vượt 20000 ký tự bị cắt phía server
    Giả sử client gửi crash log với stack trace dài 30000 ký tự
    Khi server lưu bản ghi
    Thì bản ghi trong DB có stack chỉ dài 20000 ký tự (bị cắt)
    Và server KHÔNG trả về 500

  # ─── Rate limit ──────────────────────────────────────────────────────────

  Kịch bản: Gửi quá 60 bản ghi trong 5 phút bị từ chối
    Giả sử user "ceo@a.vn" đã gửi 60 bản ghi crash log trong 5 phút qua
    Khi user gửi thêm 1 bản ghi nữa
    Thì server trả về HTTP 429 (Too Many Requests)

  Kịch bản: Rate limit không ảnh hưởng user khác trong cùng workspace
    Giả sử user "nv@a.vn" đã bị rate limit (60 bản ghi/5 phút)
    Khi user "ceo@a.vn" gửi crash log trong cùng workspace A
    Thì request của CEO vẫn được chấp nhận (200)

  # ─── Cô lập workspace ────────────────────────────────────────────────────

  Kịch bản: CEO workspace A không thấy crash log của workspace B
    Giả sử workspace B có 5 bản ghi crash log
    Khi CEO workspace A gọi GET /api/v1/crash-logs
    Thì danh sách trả về chỉ chứa crash log của workspace A

  Kịch bản: User thường bị từ chối xem danh sách crash log
    Giả sử "nv@b.vn" là user thường (không phải CEO)
    Khi "nv@b.vn" gọi GET /api/v1/crash-logs
    Thì server trả về HTTP 403

  Kịch bản: User thường bị từ chối xem summary crash log
    Giả sử "nv@b.vn" là user thường (không phải CEO)
    Khi "nv@b.vn" gọi GET /api/v1/crash-logs/summary
    Thì server trả về HTTP 403

  # ─── Summary theo fingerprint ────────────────────────────────────────────

  Kịch bản: Summary gom nhóm theo fingerprint và trả đúng thống kê
    Giả sử bảng crash_logs của workspace A có:
      | fingerprint | count | users | source |
      | "fp-abc"    | 5     | 3     | fe_js  |
      | "fp-def"    | 2     | 1     | fe_api |
    Khi CEO gọi GET /api/v1/crash-logs/summary
    Thì response chứa 2 nhóm
    Và nhóm "fp-abc" có count=5, affected_users=3, sample_message khác rỗng
    Và nhóm "fp-abc" có first_seen và last_seen là datetime hợp lệ

  # ─── BE unhandled exception ──────────────────────────────────────────────

  Kịch bản: Endpoint ném exception không xử lý được ghi vào crash_logs
    Giả sử có route /api/v1/test-crash ném RuntimeError khi được gọi
    Khi client gọi GET /api/v1/test-crash
    Thì server trả về HTTP 500
    Và bảng crash_logs có 1 bản ghi với source = "be_unhandled"
    Và bản ghi đó chứa traceback và path và method của request

  Kịch bản: HTTPException 404 KHÔNG bị ghi vào crash_logs
    Giả sử client gọi route không tồn tại → FastAPI trả 404
    Khi server xử lý
    Thì KHÔNG có bản ghi nào được thêm vào crash_logs

  Kịch bản: HTTPException 422 KHÔNG bị ghi vào crash_logs
    Giả sử client gửi body không hợp lệ → FastAPI trả 422
    Khi server xử lý
    Thì KHÔNG có bản ghi nào được thêm vào crash_logs

  Kịch bản: Việc ghi crash log thất bại không làm đổi response cho client
    Giả sử middleware không thể ghi vào DB (DB lỗi tạm thời)
    Và có route ném RuntimeError
    Khi client gọi route đó
    Thì client vẫn nhận được HTTP 500 JSON
    Và không có lỗi nào bị nuốt làm thay đổi response gốc
