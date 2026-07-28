# language: vi
# Tính năng này map về Task 1.3 (src/errors hạ tầng + ErrorBoundary + Sentry)
# Tiêu chí nghiệm thu: sprint-1.md § Task 1.3

Tính năng: ErrorBoundary chặn lỗi render và crashReporter gửi log an toàn

  Bối cảnh:
    Giả sử app đang chạy với ErrorBoundary bọc ở ngoài cùng (App.tsx)
    Và ScreenErrorBoundary bọc từng màn trong navigator

  # ─── ErrorBoundary toàn màn ──────────────────────────────────────────────

  Kịch bản: Component con ném lỗi khi render thì hiện fallback toàn màn thay vì sập app
    Giả sử có component con ném Error("test crash") khi render
    Và component đó được bọc trong ErrorBoundary
    Khi component được render
    Thì app không sập (không throw ra ngoài ErrorBoundary)
    Và màn hình hiện fallback thay vì nội dung bị lỗi
    Và crashReporter.report() được gọi với thông tin lỗi

  Kịch bản: ErrorBoundary gọi report với đầy đủ thông tin khi bắt được lỗi
    Giả sử component con ném Error("render failure")
    Khi ErrorBoundary bắt được lỗi
    Thì crashReporter.report() nhận được object có source, message, và stack

  # ─── ScreenErrorBoundary — fallback mức màn + Thử lại ───────────────────

  Kịch bản: Lỗi ở 1 màn chỉ ảnh hưởng màn đó, không làm sập toàn app
    Giả sử màn "ChatScreen" ném lỗi khi render
    Và màn "HomeScreen" đang chạy bình thường
    Khi ScreenErrorBoundary của ChatScreen bắt lỗi
    Thì HomeScreen vẫn hiển thị bình thường
    Và ChatScreen hiện fallback nhỏ với nút "Thử lại"

  Kịch bản: Bấm nút Thử lại reset boundary để màn sống lại
    Giả sử ScreenErrorBoundary của màn đang hiện fallback (sau lỗi render)
    Khi người dùng bấm nút "Thử lại"
    Thì ScreenErrorBoundary reset state
    Và màn cố gắng render lại

  # ─── Hàng đợi offline khi chưa đăng nhập ───────────────────────────────

  Kịch bản: Crash lúc chưa đăng nhập được xếp hàng trong AsyncStorage
    Giả sử người dùng CHƯA đăng nhập (chưa có JWT)
    Khi app gặp crash và crashReporter.report() được gọi
    Thì crash log KHÔNG được gửi ngay lên server
    Và crash log được lưu vào hàng đợi AsyncStorage

  Kịch bản: Đăng nhập xong thì hàng đợi được flush lên server
    Giả sử có 2 crash log đang nằm trong hàng đợi AsyncStorage (chưa gửi)
    Khi người dùng đăng nhập thành công và AuthContext gọi crashReporter.flush()
    Thì 2 bản ghi được gửi lên POST /api/v1/crash-logs
    Và hàng đợi AsyncStorage được xóa sau khi gửi thành công

  Kịch bản: Hàng đợi tối đa 50 bản ghi theo FIFO
    Giả sử hàng đợi đã chứa 50 bản ghi
    Khi crashReporter.report() được gọi thêm 1 lần nữa
    Thì bản ghi cũ nhất bị bỏ ra khỏi hàng đợi
    Và hàng đợi vẫn chỉ có 50 bản ghi

  # ─── crashReporter không bao giờ ném lỗi ────────────────────────────────

  Kịch bản: crashReporter.report() không ném lỗi kể cả khi AsyncStorage ném
    Giả sử AsyncStorage.getItem ném Error("storage failure")
    Khi crashReporter.report() được gọi
    Thì không có lỗi nào bị ném ra ngoài (không throw)

  Kịch bản: crashReporter.flush() không ném lỗi kể cả khi fetch ném
    Giả sử global.fetch ném Error("network failure")
    Khi crashReporter.flush() được gọi
    Thì không có lỗi nào bị ném ra ngoài (không throw)

  Kịch bản: crashReporter.report() không ném lỗi kể cả khi AsyncStorage.setItem ném
    Giả sử AsyncStorage.setItem ném Error("quota exceeded")
    Khi crashReporter.report() được gọi với crash log hợp lệ
    Thì không có lỗi nào bị ném ra ngoài (không throw)

  # ─── redact — lọc dữ liệu nhạy cảm ────────────────────────────────────

  Kịch bản: redact() xóa Authorization khỏi context trước khi gửi
    Giả sử context crash log có trường Authorization = "Bearer abc123"
    Khi redact() được gọi với context đó
    Thì context trả về không còn chứa Authorization header

  Kịch bản: redact() xóa refresh_token khỏi context
    Giả sử context crash log có trường refresh_token = "some-token"
    Khi redact() được gọi
    Thì context trả về không còn chứa refresh_token

  Kịch bản: redact() xóa password khỏi context
    Giả sử context crash log có trường password = "user-password"
    Khi redact() được gọi
    Thì context trả về không còn chứa password

  # ─── Sentry — im lặng khi thiếu DSN ─────────────────────────────────────

  Kịch bản: Thiếu EXPO_PUBLIC_SENTRY_DSN thì Sentry không khởi tạo và app chạy bình thường
    Giả sử biến môi trường EXPO_PUBLIC_SENTRY_DSN không được đặt (undefined)
    Khi initSentry() được gọi
    Thì Sentry.init() KHÔNG được gọi
    Và app chạy bình thường không có lỗi
