/**
 * Design tokens của app — nguồn sự thật duy nhất cho màu / spacing / chữ / font.
 * Hệ design: Grammarly (iOS) — chưng cất từ awesome-ios-design-md/…/grammarly.
 * Accent thương hiệu DUY NHẤT = Grammarly Green (#15C39A). Font: Inter.
 * Quy tắc: xem frontend/DESIGN.md. KHÔNG hardcode hex / số spacing lẻ trong màn hình;
 * import từ đây. Dark mode: token đã có sẵn (colorsDark) nhưng chưa wire — light-only.
 */
import { TextStyle } from "react-native";

// Họ font Inter (nạp qua expo-font ở App.tsx). Với custom font, chọn ĐÚNG file
// theo độ đậm — không set fontWeight kèm (tránh faux-bold trên Android).
export const fonts = {
  regular: "Inter-Regular",
  medium: "Inter-Medium",
  semibold: "Inter-SemiBold",
  bold: "Inter-Bold",
  extrabold: "Inter-ExtraBold",
} as const;

// Màu theo tỷ lệ 60/30/10: nền trung tính 60%, màu trạng thái bổ trợ 30%,
// accent thương hiệu 10% (Grammarly Green — accent duy nhất).
export const colors = {
  // 60% — nền & chữ trung tính (Grammarly light: canvas #FFF, surface1 #F7F8F8…)
  bg: "#f7f8f8",
  surface: "#ffffff",
  surfaceAlt: "#eef0f0", // bề mặt chìm hơn surface (bong bóng AI, chip)
  border: "#e4e6e6",
  borderStrong: "#d4d7d7",
  divider: "#eef0f0",
  text: "#1a1a1a", // near-black hơi ấm — KHÔNG dùng #000
  textSecondary: "#6b6b70",
  textMuted: "#9a9a9f",
  // 30% — nền/viền trạng thái (đợi, cảnh báo, lỗi) — họ vàng premium cho warning
  warningBg: "#fbf5e6",
  warningBarBg: "#f6ebcb",
  warningBorder: "#ead79a",
  warningText: "#8a6400",
  confirmBg: "#fbf3e8",
  confirmBorder: "#f0cfa0",
  dangerBg: "#fce9e9",
  // 10% — accent (Grammarly Green là accent DUY NHẤT)
  primary: "#15c39a",
  primaryDeep: "#11a683", // nhấn mạnh / gradient end
  primaryPressed: "#0e8a6d", // trạng thái nhấn nút xanh
  primaryTint: "rgba(21,195,154,0.12)", // 12% wash — nền chip/selected
  onPrimary: "#ffffff", // chữ/icon TRÊN nền xanh — dùng trắng (yêu cầu chủ dự án)
  onDanger: "#ffffff", // chữ trên nền danger
  onSuccess: "#ffffff", // chữ trên nền success
  danger: "#e5484d",
  success: "#16a34a",
  premiumGold: "#e0a82e", // CHỈ dùng cho upsell — không phải màu chức năng
  info: "#3b82f6",
} as const;

// Bộ token dark (Grammarly dark: canvas #121212 ấm, KHÔNG đen tuyền). Chưa wire.
export const colorsDark = {
  bg: "#121212",
  surface: "#1c1c1e",
  surfaceAlt: "#262629",
  border: "#2c2c2e",
  borderStrong: "#3a3a3c",
  divider: "#2c2c2e",
  text: "#e4e4e4",
  textSecondary: "#9a9a9f",
  textMuted: "#6a6a6e",
  warningBg: "#2a2410",
  warningBarBg: "#3a3214",
  warningBorder: "#5a4c1e",
  warningText: "#e0a82e",
  confirmBg: "#2a2414",
  confirmBorder: "#5a4a24",
  dangerBg: "#3a1f20",
  primary: "#15c39a",
  primaryDeep: "#11a683",
  primaryPressed: "#0e8a6d",
  primaryTint: "rgba(21,195,154,0.14)",
  onPrimary: "#06281f",
  onDanger: "#ffffff",
  onSuccess: "#ffffff",
  danger: "#f05a5f",
  success: "#22b85a",
  premiumGold: "#e0a82e",
  info: "#5a95f8",
} as const;

// Lưới 8pt (nửa bước 4 cho khe nhỏ). Không dùng giá trị ngoài thang này.
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

// Bo góc — Grammarly: pill (999) cho MỌI nút, card 16, input/list 12, chip nhỏ 8.
export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  pill: 999,
} as const;

// Bóng mềm — app phẳng, chỉ khối "nổi" mới có bóng (shadowOpacity ≤ 0.08).
export const shadow = {
  soft: {
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  card: {
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
    elevation: 4,
  },
  bar: {
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: -2 },
    elevation: 8,
  },
} as const;

// Thang chữ Grammarly (Inter). Chọn family theo độ đậm — không set fontWeight kèm.
// Các key cũ (title/heading/metric/body/caption) giữ nguyên tên để không phá màn hình.
export const type = {
  // screen title lớn nhất — "Hôm nay", "Trợ lý AI"
  screenTitle: { fontFamily: fonts.extrabold, fontSize: 32, lineHeight: 38, letterSpacing: -0.6, color: colors.text } as TextStyle,
  title: { fontFamily: fonts.extrabold, fontSize: 28, lineHeight: 34, letterSpacing: -0.5, color: colors.text } as TextStyle,
  cardTitle: { fontFamily: fonts.bold, fontSize: 18, lineHeight: 23, letterSpacing: -0.1, color: colors.text } as TextStyle,
  heading: { fontFamily: fonts.bold, fontSize: 16, lineHeight: 22, letterSpacing: -0.1, color: colors.text } as TextStyle,
  metric: { fontFamily: fonts.bold, fontSize: 24, lineHeight: 28, color: colors.text } as TextStyle,
  body: { fontFamily: fonts.regular, fontSize: 16, lineHeight: 24, color: colors.text } as TextStyle,
  bodyStrong: { fontFamily: fonts.semibold, fontSize: 16, lineHeight: 24, color: colors.text } as TextStyle,
  caption: { fontFamily: fonts.regular, fontSize: 12, lineHeight: 16, color: colors.textSecondary } as TextStyle,
  label: { fontFamily: fonts.semibold, fontSize: 13, lineHeight: 17, color: colors.textSecondary } as TextStyle,
  button: { fontFamily: fonts.bold, fontSize: 16, lineHeight: 20, color: colors.onPrimary } as TextStyle,
} as const;
