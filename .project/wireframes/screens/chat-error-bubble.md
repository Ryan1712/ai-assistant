# Wireframe: Bong bóng lỗi trong màn Chat

**Sprint**: 1 — Crash Reporting & Error Resilience
**Task liên quan**: 1.U (wireframe) → 1.4 (triển khai)
**Designer**: Emily Chen (apple-ux-wireframer)
**Ngày**: 2026-07-27
**Trạng thái**: READY FOR REVIEW

**Component triển khai**: `frontend/app/main/chat.tsx`

---

## Bối cảnh — Cấu trúc bong bóng hiện tại trong chat.tsx

Trước khi thiết kế lỗi, cần nắm rõ 3 loại bong bóng đang tồn tại:

| Loại (`kind`) | Vị trí | Nền | Hình dạng | Dùng cho |
|--------------|--------|-----|-----------|---------|
| `assistant` / `streaming` | Trái, full-width | Không nền | Văn bản thuần | Câu trả lời AI |
| `user` | Phải, max 88% | `colors.surfaceAlt` | Pill bo (`radius.xl`) | Tin nhắn người dùng |
| `system` (tool-use) | Trái, pill nhỏ | `colors.surfaceAlt` | Pill (`radius.pill`) | Tool đang chạy ("Tạo task", "Tra cứu"…) |
| `failed` (request lỗi) | Trái, pill nhỏ | `colors.dangerBg` | Pill (`radius.pill`) | AI xử lý thất bại |

Bong bóng lỗi mới (B1) phải **khác rõ** với tất cả loại trên, đặc biệt là `system` (tool-use) vì chúng cùng nằm bên trái.

---

## B1 + B2. Bong bóng lỗi API — Thiết kế tổng thể

### Wireframe — Màn chat với trạng thái lỗi API

```
 ┌──────────────────────────────────────┐
 │  9:41                      ▊▊▊ 🔋   │
 ├──────────────────────────────────────┤
 │  ☰   Trợ lý AI                  ↩   │  ← Header (giữ nguyên)
 ├──────────────────────────────────────┤
 │                                      │
 │  Xin chào! Tôi có thể giúp gì       │  ← Bong bóng AI (assistant)
 │  cho bạn hôm nay?                    │     Không nền, full-width
 │                                      │     KHÔNG có viền
 │                                      │
 │                   ┌────────────────┐ │  ← Bong bóng user (user)
 │                   │ Tạo project mới│ │     bg: colors.surfaceAlt
 │                   └────────────────┘ │     radius: radius.xl, canh phải
 │                                      │
 │  ✦ Tạo project                       │  ← System row (tool-use)
 │                                      │     pill nhỏ, surfaceAlt, textSecondary
 │                                      │
 │ ┌──────────────────────────────────┐ │  ← BỌ̃NG BÓ̃NG LỖI MỚI (B1/B2)
 │ │ ⚠  Hệ thống đang có lỗi,        │ │     bg: colors.dangerBg
 │ │    vui lòng thử lại.             │ │     border: 1pt colors.dangerBorder*
 │ │                                  │ │     radius: radius.md (12)
 │ │              [  Thử lại  ]       │ │     KHÔNG phải pill nhỏ
 │ └──────────────────────────────────┘ │     (*token cần thêm — xem Ghi chú)
 │                                      │
 ├──────────────────────────────────────┤
 │ ┌────────────────────────────────┐   │  ← Input box (B4)
 │ │ Tạo project mới_               │   │     Text của user vẫn còn đây
 │ └────────────────────────────────┘   │     (setInput giữ nguyên content)
 │  [+]                        [🎤][▲] │
 └──────────────────────────────────────┘
```

### So sánh trực quan — Tool-use vs Error bubble

```
 TOOL-USE (system row hiện tại):
 ┌─────────────────────────────┐
 │✦ Tạo project                │  ← pill nhỏ, surfaceAlt
 └─────────────────────────────┘

 ERROR BUBBLE (mới):
 ┌──────────────────────────────────────────┐
 │ ⚠  Hệ thống đang có lỗi,                │  ← card rộng hơn, dangerBg
 │    vui lòng thử lại.                     │     border dangerBorder, radius.md
 │                            [  Thử lại  ] │     icon lớn hơn (16pt)
 └──────────────────────────────────────────┘
```

Sự khác biệt có chủ đích:
- **Hình dạng**: Tool-use = pill tròn nhỏ / Error = card chữ nhật bo góc `radius.md`
- **Nền**: Tool-use = `colors.surfaceAlt` (xám) / Error = `colors.dangerBg` (đỏ nhạt)
- **Viền**: Tool-use = không viền / Error = 1pt `colors.dangerBorder`
- **Icon**: Tool-use = `sparkles-outline` 15pt / Error = `alert-circle` 16pt (filled)
- **Có nút**: Tool-use = không / Error = có nút "Thử lại" inline

---

## B3. Nút "Thử lại" trong bong bóng lỗi

### Hành vi khi nhấn "Thử lại"

Nút "Thử lại" trong bong bóng lỗi API phải thực hiện:
1. Xóa bong bóng lỗi đó khỏi `rows`
2. Gọi lại `submit()` với content đang có trong `input` (text đã được giữ lại từ `setInput(content)`)

**Lưu ý triển khai**: Bong bóng lỗi cần lưu kèm `retryContent` (text người dùng đã gõ) trong `Row`, tương tự cách `kind: "failed"` đang lưu `retryContent`. Khi nhấn "Thử lại", gọi `submit(retryContent)` và xóa bong bóng.

### Chi tiết nút

```
 ┌───────────────────────────────────────────┐
 │                              ┌──────────┐ │
 │  ⚠  Hệ thống đang có lỗi,   │ Thử lại  │ │
 │     vui lòng thử lại.        └──────────┘ │
 └───────────────────────────────────────────┘
                                ↑
                         Ghost danger style:
                         border 1.5pt colors.danger
                         text colors.danger
                         radius: radius.pill
                         padding: spacing.sm × spacing.md
                         height: 32pt (đủ 44pt khi tính hitSlop 6)
```

| Thành phần nút | Token |
|---------------|-------|
| Viền | `colors.danger`, 1.5pt |
| Chữ | `colors.danger`, `type.label` (semibold 13) |
| Nền | Trong suốt |
| Bo góc | `radius.pill` |
| Kích thước chạm | Thêm `hitSlop={6}` để đạt 44pt |

---

## B4. Trạng thái tin nhắn người dùng khi gửi thất bại

### Nguyên tắc

Khi `submit()` throw exception (API 500 / timeout / mất mạng), `chat.tsx` hiện tại đã thực hiện `setInput(content)` — tức là text người dùng đã gõ được trả về ô nhập. Đây là hành vi **đúng và đủ** — không cần hiển thị bubble "pending" riêng.

Lý do không dùng "pending bubble" ở phía user:
- Nếu dùng pending bubble (xám, có spinner), UX phức tạp hơn — phải quản lý thêm state "pending → success/fail"
- Text trong input box là đủ để người dùng biết "nội dung chưa gửi được, đang chờ tôi gõ lại / thử lại"
- Nút "Thử lại" trong error bubble đã cover action cần thiết

### Wireframe — Input box sau khi gửi thất bại

```
 ┌────────────────────────────────────────────────┐
 │ Tạo project mới cho team marketing_            │  ← Text quay về input
 │                                                │     user thấy ngay nội dung
 │                                                │     chưa mất
 └────────────────────────────────────────────────┘
  [+]                                    [🎤]  [▲]
                                               ↑
                                         Nút gửi active (canSend = true)
                                         vì input có text
```

### Bảng trạng thái B4

| Trạng thái | Input box | Bong bóng lỗi | Nút gửi |
|-----------|----------|--------------|--------|
| Đang gửi | Disabled (hoặc không) | Chưa có | Spinner / disabled |
| Gửi thành công | Rỗng | Không có | Disabled (canSend=false) |
| Gửi thất bại | **Có text** (setInput) | Xuất hiện bên dưới | Active (canSend=true) |
| Sau khi thử lại thành công | Rỗng | Biến mất | Disabled |

---

## B5. Phân biệt với mất mạng kéo dài — Offline Banner

### Quan điểm thiết kế

Khi mất mạng kéo dài, nếu dùng bong bóng lỗi cho mỗi lần gửi thất bại, màn chat sẽ bị lấp đầy bằng các bong bóng đỏ lặp đi lặp lại — gây hoảng loạn và mất tín hiệu hữu ích. Cần phân biệt hai trường hợp:

| Trường hợp | Trigger | UI pattern |
|-----------|---------|-----------|
| Gửi 1 tin thất bại (API lỗi thoáng qua) | Catch trong `submit()` | Bong bóng lỗi đơn + "Thử lại" |
| Mất mạng kéo dài (nhiều lần liên tiếp thất bại, hoặc NetInfo offline) | NetInfo event HOẶC ≥ 2 lần thất bại liên tiếp | Sticky banner đầu danh sách — thay bong bóng lỗi |

### Wireframe — Offline Banner

```
 ┌──────────────────────────────────────┐
 │  9:41                      ▊▊▊ 🔋   │
 ├──────────────────────────────────────┤
 │  ☰   Trợ lý AI                  ↩   │
 ├──────────────────────────────────────┤
 │ ─────────────────────────────────── │
 │  📶  Đang mất kết nối —             │  ← Offline Banner
 │      Tin nhắn sẽ được gửi khi        │     bg: colors.warningBg
 │      có mạng trở lại.               │     border bottom: colors.warningBorder
 │ ─────────────────────────────────── │     text: colors.warningText
 │                                      │     icon: wifi-outline (Ionicons)
 │  (Tin nhắn AI trước đó)             │
 │                                      │
 │                   ┌────────────────┐ │
 │                   │ Tạo project mới│ │  ← Tin gửi thất bại vẫn nằm
 │                   └────────────────┘ │     trong input, KHÔNG hiện thêm
 │                                      │     bong bóng đỏ nữa (đã có banner)
 ├──────────────────────────────────────┤
 │ ┌────────────────────────────────┐   │
 │ │ Tạo project mới_               │   │  ← Text trong input, user thấy
 │ └────────────────────────────────┘   │     đang chờ kết nối để gửi
 └──────────────────────────────────────┘
```

### Bảng token Offline Banner

| Thành phần | Token |
|-----------|-------|
| Nền banner | `colors.warningBg` |
| Viền dưới | `colors.warningBorder` |
| Icon wifi | `colors.warningText` |
| Chữ | `colors.warningText`, `type.caption` |
| Padding | `spacing.lg` ngang, `spacing.sm` dọc |

### Lý do dùng warning (vàng) thay vì danger (đỏ) cho offline banner

Banner mất mạng là **tình trạng tạm thời** — app vẫn hoạt động, chỉ tính năng gửi bị pause. Màu warning (vàng/amber) truyền đúng thông điệp "chú ý, có điều bất thường nhưng không nguy hiểm". Màu danger (đỏ) nên dành cho lỗi cần hành động ngay của người dùng (ví dụ: lỗi không retry được).

---

## Bảng trạng thái tổng hợp — Màn chat

| Trạng thái | Hiển thị | Hành động khả dụng |
|-----------|---------|-------------------|
| Bình thường | Bong bóng AI + user + tool-use | Gõ và gửi tin |
| Đang gửi | User bubble + spinner/indicator nhỏ | Không gửi thêm (nút disabled tạm) |
| Gửi thất bại (1 lần, có mạng) | Error bubble đỏ + text trong input | "Thử lại" trong error bubble |
| Gửi thất bại (mất mạng) | Offline banner vàng + text trong input | Chờ mạng; banner tự ẩn khi online |
| AI xử lý thất bại (`request_failed`) | `failed` row đỏ (pill, style hiện tại) | "Gửi lại" (set input với content cũ) |
| Mất kết nối WS | `actionError` bar hiện tại ("Mất kết nối realtime…") | Kéo xuống để tải lại |

---

## Phân biệt 2 loại lỗi trong chat (tóm tắt)

| | Lỗi API khi gửi (mới — B1) | AI xử lý thất bại (hiện tại — `failed`) |
|--|---------------------------|----------------------------------------|
| Trigger | `submit()` catch: 500 / timeout / mạng | WS event `request_failed` |
| Message | "Hệ thống đang có lỗi, vui lòng thử lại." | `friendlyError(e.error)` — mô tả cụ thể hơn |
| Nút | "Thử lại" → `submit(retryContent)` | "Gửi lại" → `setInput(retryContent)` |
| Hình dạng | Card `radius.md`, `dangerBg` + border | Pill `radius.pill`, `dangerBg` (style hiện tại) |
| Kind | Đề xuất: `"apierror"` (Row mới) | `"failed"` (đã có) |

---

## Ghi chú token thiếu (nhắc lại từ error-fallback.md)

| Token thiếu | Cần ở đâu trong file này | Đề xuất giá trị |
|------------|------------------------|----------------|
| `colors.dangerBorder` | Viền card error bubble (B1/B2) | `"#f5b5b7"` |
| `colors.dangerText` | Chữ body trên `dangerBg` (nếu cần tối hơn `danger`) | `"#c0262b"` |

**Cách xử lý tạm khi token chưa được thêm vào theme.ts**:
- Viền: bỏ viền, chỉ dùng `dangerBg` làm phân biệt (chấp nhận được)
- Chữ body: dùng `colors.text` (#1a1a1a) thay vì `colors.danger` — tương phản tốt trên `dangerBg`
- KHÔNG hardcode hex trong code component

---

## Ghi chú accessibility — Bong bóng lỗi

| Mục | Yêu cầu |
|-----|---------|
| Vùng chạm "Thử lại" | Tối thiểu 44pt — thêm `hitSlop={6}` nếu nút nhỏ |
| `accessibilityLabel` nút | `"Thử lại gửi tin nhắn"` |
| `accessibilityRole` nút | `"button"` |
| `accessibilityLiveRegion` error bubble | `"polite"` — screen reader thông báo khi bubble xuất hiện mà không ngắt |
| Màu sắc | Icon `colors.danger` đủ tương phản trên `colors.dangerBg`. Chữ body dùng `colors.text` (không dùng `colors.danger` cho body text — tương phản kém) |
| Offline banner | `accessibilityLiveRegion="assertive"` — thông báo ngay lập tức khi mất mạng |

---

## Câu chữ chốt (không được thay đổi)

> **"Hệ thống đang có lỗi, vui lòng thử lại."**

Đây là câu do client chốt (Task 1.4 Acceptance Criteria). Giữ nguyên 100%.

**Biến thể đề xuất** (chỉ dùng nếu client cho phép thay đổi trong tương lai):
- "Không thể gửi tin lúc này. Vui lòng thử lại." — ngắn hơn, tập trung vào hành động
- "Gửi không thành công. Thử lại hoặc kiểm tra kết nối mạng." — thêm gợi ý chẩn đoán

Lưu ý: cả hai biến thể đề xuất chưa được approve — **không triển khai** cho đến khi client xác nhận.
