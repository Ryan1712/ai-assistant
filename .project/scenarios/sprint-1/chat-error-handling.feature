# language: vi
# Tính năng này map về Task 1.4 (chat báo lỗi thân thiện + apiFetch báo cáo lỗi)
# Tiêu chí nghiệm thu: sprint-1.md § Task 1.4

Tính năng: Chat hiển thị lỗi thân thiện và apiFetch ghi log lỗi đúng loại

  Bối cảnh:
    Giả sử người dùng đã đăng nhập vào chat
    Và giao diện chat đang hiển thị bình thường

  # ─── API 500 khi gửi tin nhắn ───────────────────────────────────────────

  Kịch bản: API trả về 500 khi gửi tin nhắn thì hiện thông báo lỗi thân thiện
    Giả sử POST /api/v1/chat/messages trả về HTTP 500
    Khi người dùng gửi tin nhắn
    Thì khung chat hiện "Hệ thống đang có lỗi, vui lòng thử lại."
    Và app KHÔNG sập
    Và app KHÔNG chuyển màn hình ra màn login

  Kịch bản: Sau lỗi 500 người dùng vẫn có thể gửi lại tin nhắn
    Giả sử lần gửi đầu tiên bị lỗi 500 và hiện thông báo lỗi
    Khi server phục hồi và người dùng gửi lại tin nhắn
    Thì tin nhắn được gửi thành công
    Và thông báo lỗi biến mất

  # ─── Mất mạng khi gửi tin nhắn ──────────────────────────────────────────

  Kịch bản: Mất mạng khi gửi tin nhắn thì hiện cùng thông báo lỗi
    Giả sử fetch ném NetworkError (mất kết nối Internet)
    Khi người dùng gửi tin nhắn
    Thì khung chat hiện "Hệ thống đang có lỗi, vui lòng thử lại."
    Và app KHÔNG sập

  Kịch bản: Mất mạng khi gửi tin nhắn thì có nút thử lại
    Giả sử fetch ném NetworkError
    Khi người dùng gửi tin nhắn
    Thì khung chat hiện nút "Thử lại" bên cạnh thông báo lỗi

  # ─── 401 vẫn đi luồng refresh token ─────────────────────────────────────

  Kịch bản: API trả 401 thì đi luồng refresh token cũ, không hiện lỗi hệ thống
    Giả sử POST /api/v1/chat/messages trả về HTTP 401 (access token hết hạn)
    Và refresh token còn hiệu lực
    Khi apiFetch xử lý response 401
    Thì apiFetch tự gọi tryRefresh() rồi thử lại request
    Và KHÔNG hiện "Hệ thống đang có lỗi, vui lòng thử lại." trong chat
    Và crashReporter.report() KHÔNG được gọi

  Kịch bản: 401 khi refresh token cũng hết hạn thì đăng xuất, không hiện lỗi hệ thống
    Giả sử access token hết hạn VÀ refresh token cũng hết hạn
    Khi apiFetch nhận 401 và tryRefresh() trả về false
    Thì người dùng bị điều hướng ra màn đăng nhập theo luồng cũ
    Và crashReporter.report() KHÔNG được gọi

  # ─── Không log 4xx thường ────────────────────────────────────────────────

  Kịch bản: Lỗi 403 (Forbidden) không được ghi vào crash log
    Giả sử apiFetch nhận về HTTP 403
    Khi apiFetch xử lý response
    Thì crashReporter.report() KHÔNG được gọi

  Kịch bản: Lỗi 404 (Not Found) không được ghi vào crash log
    Giả sử apiFetch nhận về HTTP 404
    Khi apiFetch xử lý response
    Thì crashReporter.report() KHÔNG được gọi

  Kịch bản: Lỗi 422 (Validation Error) không được ghi vào crash log
    Giả sử apiFetch nhận về HTTP 422
    Khi apiFetch xử lý response
    Thì crashReporter.report() KHÔNG được gọi

  Kịch bản: Lỗi 5xx được ghi vào crash log
    Giả sử apiFetch nhận về HTTP 500
    Khi apiFetch xử lý response
    Thì crashReporter.report() ĐƯỢC gọi với source = "fe_api"

  Kịch bản: Timeout được ghi vào crash log
    Giả sử fetch ném AbortError (timeout)
    Khi apiFetch xử lý lỗi
    Thì crashReporter.report() ĐƯỢC gọi với source = "fe_api"

  Kịch bản: Lỗi mạng (NetworkError) được ghi vào crash log
    Giả sử fetch ném TypeError (mất mạng)
    Khi apiFetch xử lý lỗi
    Thì crashReporter.report() ĐƯỢC gọi với source = "fe_api"

  # ─── Không đệ quy (gửi crash log thất bại không sinh crash log mới) ─────

  Kịch bản: Gửi crash log thất bại không sinh thêm crash log mới
    Giả sử postCrashLogs() (fetch trần) ném lỗi mạng
    Khi crashReporter.flush() gọi postCrashLogs() và nhận lỗi
    Thì crashReporter KHÔNG gọi report() bên trong flush()
    Và không có vòng lặp đệ quy nào xảy ra

  Kịch bản: postCrashLogs dùng fetch trần không đi qua apiFetch
    Giả sử postCrashLogs() được gọi để gửi crash logs
    Khi postCrashLogs() thực thi
    Thì nó dùng global.fetch trực tiếp
    Và KHÔNG gọi apiFetch (để tránh đệ quy log)
