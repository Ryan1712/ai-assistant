# Wireframe: Màn hình lỗi — Error Fallback

**Sprint**: 1 — Crash Reporting & Error Resilience
**Task liên quan**: 1.U (wireframe) → 1.3 (triển khai)
**Designer**: Emily Chen (apple-ux-wireframer)
**Ngày**: 2026-07-27
**Trạng thái**: READY FOR REVIEW

**Component triển khai**:
- A1 → `frontend/src/errors/ErrorBoundary.tsx`
- A2 → `frontend/src/errors/ScreenErrorBoundary.tsx`

---

## A1. Fallback toàn màn — ErrorBoundary gốc (bọc App.tsx)

**Kịch bản**: Lỗi render lan từ cây component con lên đến root. Toàn bộ UI sập — không còn header, tab bar, navigation. Nếu không có màn này, người dùng nhìn thấy màn trắng hoàn toàn.

**Nguyên tắc**: Trấn an trước, thông tin kỹ thuật không bao giờ xuất hiện. Hành động chính duy nhất là "Tải lại". Mã sự cố ngắn để hỗ trợ tra cứu khi cần — xem phần Quyết định thiết kế.

### Wireframe (390pt × 844pt — iPhone 14)

```
 ┌──────────────────────────────────────┐
 │  9:41                      ▊▊▊ 🔋   │  ← Safe area top (44pt)
 │                                      │
 │                                      │
 │                                      │
 │                                      │
 │                   ✦                  │  ← Icon ứng dụng / spark
 │                                      │     Ionicons "sparkles"
 │                                      │     size 48, colors.primary
 │                                      │
 │         Có gì đó chưa ổn            │  ← type.title (28/34 bold)
 │                                      │     colors.text
 │                                      │
 │    Ứng dụng gặp sự cố không          │  ← type.body (16/24 regular)
 │    mong muốn. Nhóm kỹ thuật          │     colors.textSecondary
 │    đã được tự động thông báo.        │     padding ngang: spacing.xl
 │                                      │
 │                                      │
 │  ┌────────────────────────────────┐  │  ← Nút chính — THUMB ZONE
 │  │      Tải lại ứng dụng          │  │     backgroundColor: colors.primary
 │  └────────────────────────────────┘  │     borderRadius: radius.pill
 │                                      │     height: 52pt (≥ 44pt touch)
 │                                      │     marginHorizontal: spacing.xl
 │                                      │
 │  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  │  ← Divider mờ (colors.divider)
 │                                      │
 │         Mã sự cố: A3F2·91           │  ← type.caption (12/16)
 │    (đọc cho bộ phận hỗ trợ nếu       │     colors.textMuted
 │     được yêu cầu)                    │     căn giữa
 │                                      │
 └──────────────────────────────────────┘
   Safe area bottom (34pt — iPhone với notch)
```

### Chú thích từng vùng

| Vùng | Mô tả | Chi tiết |
|------|-------|---------|
| Safe area top | Vùng status bar iOS | Dùng `insets.top` từ `useSafeAreaInsets()` |
| Icon ✦ | Tín hiệu "đây là app này" | `Ionicons name="sparkles"` size 48, `colors.primary` — KHÔNG dùng biểu tượng lỗi/nguy hiểm |
| Tiêu đề | Câu trấn an, ngôn ngữ người dùng | `type.title`, `colors.text`, căn giữa |
| Mô tả | Giải thích + cam kết đã ghi nhận | `type.body`, `colors.textSecondary`, 2–3 dòng tối đa |
| Nút "Tải lại" | Hành động chính, duy nhất | `colors.primary`, pill, full-width - `spacing.xl` padding ngang |
| Divider | Tách hành động chính khỏi thông tin phụ | `colors.divider`, height 1 |
| Mã sự cố | Dùng khi liên lạc hỗ trợ | `type.caption`, `colors.textMuted`, xem Quyết định A |

### Bảng token

| Thành phần | Token màu | Token spacing/radius | Token chữ |
|-----------|-----------|---------------------|-----------|
| Nền màn hình | `colors.bg` | — | — |
| Icon spark | `colors.primary` | size 48 | — |
| Tiêu đề | `colors.text` | `spacing.xl` ngang | `type.title` |
| Mô tả | `colors.textSecondary` | `spacing.xl` ngang | `type.body` |
| Nút "Tải lại" | bg `colors.primary`, text `colors.onPrimary` | `radius.pill`, h 52, mx `spacing.xl` | `type.button` |
| Divider | `colors.divider` | my `spacing.lg` | — |
| Mã sự cố | `colors.textMuted` | — | `type.caption` |

### Bảng trạng thái

| Trạng thái | Hiển thị | Hành động khả dụng |
|-----------|---------|-------------------|
| Lỗi render (mặc định) | Màn fallback đầy đủ như wireframe | "Tải lại ứng dụng" |
| Đang tải lại | Nút disabled + `ActivityIndicator` nhỏ trên nút | Không có (chờ) |
| Tải lại thành công | App render lại bình thường | — (màn này biến mất) |

### Quyết định thiết kế A: Có hay không có mã sự cố?

**Quyết định: CÓ.** Mã sự cố ngắn (8 ký tự) được hiển thị.

**Lý do**:
- Khi user gọi hỗ trợ, họ cần cung cấp context để support tra trong `crash_logs`. Mã ngắn (ví dụ `A3F2·91`) giúp support lọc ngay theo `fingerprint` hoặc `client_event_id`.
- Hiển thị kiểu `type.caption` + `colors.textMuted` — đặt dưới divider, rất khiêm tốn. Không gây lo lắng nếu user không cần dùng tới.
- KHÔNG phải stack trace, KHÔNG phải tên lỗi kỹ thuật — chỉ là mã tra cứu ngắn.

**Cách sinh mã**: `ErrorBoundary` hash `error.message + componentStack` → lấy 8 ký tự đầu (giống fingerprint trong `crashReporter`). Format hiển thị: 4 ký tự + dấu `·` + 2 ký tự (ví dụ: `A3F2·91`).

**Không có mã sự cố trong A2** (ScreenErrorBoundary): Lỗi đơn màn ít nghiêm trọng hơn, user tự "Thử lại" được mà không cần support.

### Ghi chú accessibility

| Mục | Yêu cầu |
|-----|---------|
| Vùng chạm nút "Tải lại" | Tối thiểu 52pt chiều cao — vượt yêu cầu 44pt |
| `accessibilityLabel` nút | `"Tải lại ứng dụng"` |
| `accessibilityRole` nút | `"button"` |
| `accessibilityHint` nút | `"Khởi động lại ứng dụng để khắc phục sự cố"` |
| Độ tương phản | Chữ `colors.text` (#1a1a1a) trên `colors.bg` (#f7f8f8): đạt WCAG AA (≈ 17:1) |
| Chữ mã sự cố | `colors.textMuted` (#9a9a9f) trên `colors.bg` (#f7f8f8): tương phản thấp — chấp nhận được vì đây là thông tin phụ không bắt buộc đọc |
| `accessibilityLiveRegion` | Không cần — đây là màn tĩnh, không có update liên tục |

---

## A2. Fallback mức màn hình — ScreenErrorBoundary

**Kịch bản**: Một màn hình duy nhất bị lỗi render (ví dụ: Chat, Settings). Header và tab bar vẫn sống, user vẫn điều hướng được sang màn khác. Chỉ vùng `Stack.Screen` content bị thay bởi fallback này.

**Nguyên tắc**: Nhỏ gọn, không chiếm toàn bộ không gian. Giữ nguyên chrome (header, tab) để user không cảm thấy "mắc kẹt". Nút "Thử lại" reset đúng ErrorBoundary đó (không reload cả app).

### Wireframe

```
 ┌──────────────────────────────────────┐
 │  9:41                      ▊▊▊ 🔋   │  ← Safe area top
 ├──────────────────────────────────────┤
 │  ☰   Trợ lý AI                  ↩   │  ← Header giữ nguyên
 ├──────────────────────────────────────┤
 │                                      │
 │                                      │  ← Vùng này thay thế
 │                                      │     nội dung màn hình
 │          ⚠                           │  ← Ionicons "alert-circle"
 │                                      │     size 36, colors.danger
 │   Màn hình này gặp sự cố            │  ← type.heading (16/22 bold)
 │                                      │     colors.text
 │   Không tải được nội dung.           │  ← type.body (16/24)
 │   Thử lại hoặc chuyển sang          │     colors.textSecondary
 │   màn khác.                          │
 │                                      │
 │         ┌───────────────┐            │  ← Nút "Thử lại"
 │         │    Thử lại    │            │     ghost style (border)
 │         └───────────────┘            │     KHÔNG dùng primary
 │                                      │     (hành động phụ)
 │                                      │
 │                                      │
 ├──────────────────────────────────────┤
 │     🏠 Home    💬 Chat    ⋯ More     │  ← Tab bar giữ nguyên
 └──────────────────────────────────────┘
   Safe area bottom
```

### Chú thích từng vùng

| Vùng | Mô tả | Chi tiết |
|------|-------|---------|
| Header | Giữ nguyên — user phải thoát được | Không bị thay bởi ErrorBoundary |
| Tab bar | Giữ nguyên — user phải thoát được | Không bị thay bởi ErrorBoundary |
| Icon ⚠ | Tín hiệu lỗi nhưng KHÔNG nguy hiểm | `Ionicons "alert-circle"` size 36, `colors.danger` |
| Tiêu đề | Ngắn, không kỹ thuật | `type.heading`, `colors.text` |
| Mô tả | Gợi ý hành động | `type.body`, `colors.textSecondary` |
| Nút "Thử lại" | Ghost style, không phải primary | Xem lý do bên dưới |

### Lý do nút "Thử lại" dùng ghost style thay vì primary

`ScreenErrorBoundary` là trạng thái thất bại (thứ yếu). Dùng nút primary (xanh Grammarly) sẽ tạo cảm giác "thành công" không phù hợp. Ghost danger (border đỏ) hoặc ghost neutral (border `colors.borderStrong`) phù hợp hơn. Ở đây dùng ghost neutral vì border đỏ quá mạnh với lỗi đơn màn ít nghiêm trọng.

### Bảng token

| Thành phần | Token màu | Token spacing/radius | Token chữ |
|-----------|-----------|---------------------|-----------|
| Nền vùng fallback | `colors.bg` | flex 1 | — |
| Icon ⚠ | `colors.danger` | size 36, mb `spacing.lg` | — |
| Tiêu đề | `colors.text` | `spacing.xl` ngang | `type.heading` |
| Mô tả | `colors.textSecondary` | `spacing.xl` ngang | `type.body` |
| Nút "Thử lại" | border `colors.borderStrong`, text `colors.text` | `radius.pill`, h 44, px `spacing.xl` | `type.button` (nhưng `colors.text`) |

### Bảng trạng thái

| Trạng thái | Hiển thị | Hành động khả dụng |
|-----------|---------|-------------------|
| Màn bị lỗi | Fallback như wireframe | "Thử lại" reset boundary; tab bar điều hướng sang màn khác |
| Đang thử lại | Spinner nhỏ thay icon ⚠ | Không có (chờ) |
| Thử lại thành công | Màn render bình thường | — (fallback ẩn đi) |
| Thử lại thất bại liên tục (≥ 3 lần) | Thêm dòng phụ: "Sự cố vẫn tiếp diễn. Thử tải lại toàn ứng dụng." + nút nhỏ "Tải lại ứng dụng" | "Tải lại ứng dụng" (gọi lên `ErrorBoundary` cha) |

### Ghi chú accessibility

| Mục | Yêu cầu |
|-----|---------|
| Vùng chạm "Thử lại" | Tối thiểu 44pt chiều cao |
| `accessibilityLabel` | `"Thử lại màn hình"` |
| `accessibilityRole` | `"button"` |
| Focus | Khi ErrorBoundary render fallback, dùng `AccessibilityInfo.setAccessibilityFocus` vào tiêu đề để screen reader đọc ngay |
| Header/tab bar | Vẫn accessible — không bị trap focus trong fallback |

---

## Ghi chú thiếu token

> **Phát hiện khi thiết kế — cần thêm vào `frontend/src/ui/theme.ts` trước khi triển khai**:

| Token thiếu | Dùng ở đâu | Đề xuất giá trị | Lý do |
|------------|-----------|----------------|-------|
| `colors.dangerBorder` | Viền bong bóng lỗi (xem `chat-error-bubble.md`) | `"#f5b5b7"` (pha giữa `dangerBg` và `danger`) | Cặp `warningBg`/`warningBorder` và `confirmBg`/`confirmBorder` đều có token viền — danger nên nhất quán |
| `colors.dangerText` | Chữ body trên nền `dangerBg` | `"#c0262b"` (tối hơn `danger` 20%) | `colors.danger` (#e5484d) trên `dangerBg` (#fce9e9) có tương phản kém (~2.3:1, không đạt WCAG AA 4.5:1 cho body text). Cần variant tối hơn. |

**Xử lý tạm thời cho đến khi token được thêm**: Dùng `colors.text` (#1a1a1a) cho text body trên nền `dangerBg`, chỉ dùng `colors.danger` cho icon và label "Lỗi" nhỏ. Không được hardcode hex.
