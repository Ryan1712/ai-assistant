# Design guideline — FE mobile (Expo / React Native StyleSheet)

> **Hệ design hiện tại (từ 2026-07-21): Grammarly (iOS).** Accent DUY NHẤT = Grammarly
> Green `#15C39A`; font **Inter**; nút **pill** (radius 999); card bo **16**. Nguồn:
> awesome-ios-design-md `productivity/grammarly` (bản DESIGN-expo.md). Điều hướng dùng
> **react-navigation** (native-stack, hiệu ứng iOS slide) — KHÔNG còn expo-router.
> Token cụ thể ở `src/ui/theme.ts` — **mọi màn hình import từ đó, không hardcode hex/số
> spacing**. (Lưu ý: `docs/expo-DESIGN.md` là bản scrape trang marketing expo.dev, KHÔNG
> phải design system của app — đừng dùng.)

Các quy tắc quy trình bên dưới (4 trạng thái bắt buộc, thumb zone, 60/30/10, accessibility)
vẫn áp dụng nguyên vẹn — chỉ khác bảng token màu/chữ/bo góc (nay theo Grammarly, xem
`theme.ts`). Phần dưới chưng cất từ [ceorkm/mobile-app-ui-design](https://github.com/ceorkm/mobile-app-ui-design)
(MIT) là hệ token cũ, giữ để tham chiếu quy trình.

## Quy trình khi làm màn hình mới (5 bước)

1. **Hiểu ngữ cảnh** — màn này phục vụ hành động chính nào? Người dùng đang ở giai đoạn nào
   (mới vào / dùng hàng ngày)? Convention ngành của loại màn này (chat, dashboard, form)?
2. **UX trước** — vẽ flow, xác định phần tử tối thiểu. Hành động chính đặt trong
   **thumb zone** (nửa dưới màn hình, tầm ngón cái); thông tin đọc theo thứ tự F từ trên xuống.
3. **UI sau** — áp token: chữ, màu, spacing từ `theme.ts`. Không phát minh giá trị mới tại chỗ.
4. **Cảm xúc (peak-end)** — khoảnh khắc "xong việc" (gửi tin, lưu ghi âm, tạo xong công ty)
   cần phản hồi rõ ràng, tích cực; đừng để thành công diễn ra im lặng.
5. **Đánh bóng** — đủ 4 trạng thái, accessibility, rồi mới xong.

## Quy tắc cứng

### Màu — 60/30/10
- 60% trung tính (`bg`, `surface`, `border*`, `text*`), 30% màu trạng thái
  (`warning*`, `confirm*`, `dangerBg`), 10% accent (`primary`, `danger`, `success`).
- Phân cấp chữ bằng 3 mức có sẵn: `text` (chính) → `textSecondary` (phụ) → `textMuted` (placeholder/empty).
- Muốn thêm màu mới → thêm token vào `theme.ts` kèm lý do, không inline.

### Spacing — lưới 8pt
- Chỉ dùng thang `spacing` (4/8/12/16/24/32). Khoảng cách giữa các **nhóm không liên quan**
  gấp ~2 lần khoảng cách **trong nhóm** (ví dụ: trong card dùng `sm`/`md`, giữa các card dùng `md`/`lg`).

### Chữ — 4 cỡ, 2 độ đậm
- `title` 28 / `metric` 24 / `heading` + `body` 16 / `caption` 12; đậm chỉ 400 hoặc 700.
- Số liệu nổi bật (counter, mã mời) dùng `metric`.

### Bề mặt & bóng
- App dùng phong cách phẳng: card = `surface` + `radius.lg`, phân tách bằng `border`/`divider`.
- Nếu cần bóng: bóng **mềm** (shadowOpacity ≤ 0.08, elevation ≤ 2), không bao giờ bóng gắt.

### 4 trạng thái bắt buộc mỗi khối dữ liệu
- **Loading** (spinner/skeleton), **Empty** (câu gợi ý hành động, màu `textMuted`),
  **Error** (nói được vì sao + làm gì tiếp, màu `danger`), **Success/Data**.
- Không để màn trắng hoặc lỗi câm.

### Accessibility
- Nút chỉ có icon/glyph phải có `accessibilityLabel`.
- Chữ trên nền màu phải giữ tương phản (chữ trắng chỉ đặt trên `primary`/`danger`/`success`).
- Vùng chạm tối thiểu ~44pt cho hành động chính.

## Checklist review nhanh (trước khi commit UI)
- [ ] Không còn hex/số spacing lẻ inline — tất cả từ `theme.ts`
- [ ] Hành động chính nằm trong thumb zone
- [ ] Đủ loading/empty/error/success cho khối dữ liệu mới
- [ ] Nút icon có accessibilityLabel
- [ ] Khoảnh khắc thành công có phản hồi
