/**
 * Design tokens của app — nguồn sự thật duy nhất cho màu / spacing / chữ.
 * Quy tắc sử dụng: xem frontend/DESIGN.md. Không hardcode hex hay số spacing
 * lẻ trong màn hình; import từ đây.
 */
import { TextStyle } from "react-native";

// Màu theo tỷ lệ 60/30/10: nền trung tính 60%, màu trạng thái bổ trợ 30%,
// accent thương hiệu 10%.
export const colors = {
  // 60% — nền & chữ trung tính
  bg: "#f9fafb",
  surface: "#ffffff",
  surfaceAlt: "#e5e7eb", // bề mặt chìm hơn surface (bong bóng AI, chip)
  border: "#e5e7eb",
  borderStrong: "#d1d5db",
  divider: "#f3f4f6",
  text: "#111827",
  textSecondary: "#6b7280",
  textMuted: "#9ca3af",
  // 30% — nền/viền trạng thái (đợi, cảnh báo, lỗi)
  warningBg: "#fffbeb",
  warningBarBg: "#fef3c7",
  warningBorder: "#fde68a",
  warningText: "#92400e",
  confirmBg: "#fff7ed",
  confirmBorder: "#fdba74",
  dangerBg: "#fee2e2",
  // 10% — accent
  primary: "#2563eb",
  onPrimary: "#ffffff",
  danger: "#dc2626",
  success: "#16a34a",
} as const;

// Lưới 8pt (nửa bước 4 cho khe nhỏ). Không dùng giá trị ngoài thang này.
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const radius = {
  sm: 8,
  md: 10,
  lg: 12,
} as const;

// 4 cỡ chữ, 2 độ đậm (400/700) — không thêm cỡ/độ đậm mới trong màn hình.
export const type = {
  title: { fontSize: 28, fontWeight: "700", color: colors.text } as TextStyle,
  heading: { fontSize: 16, fontWeight: "700", color: colors.text } as TextStyle,
  metric: { fontSize: 24, fontWeight: "700", color: colors.text } as TextStyle,
  body: { fontSize: 16, fontWeight: "400", color: colors.text } as TextStyle,
  caption: { fontSize: 12, fontWeight: "400", color: colors.textSecondary } as TextStyle,
} as const;
