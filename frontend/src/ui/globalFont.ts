/**
 * Đặt Inter-Regular làm font mặc định cho <Text>/<TextInput> KHÔNG có style prop.
 *
 * Cách tiếp cận: Text.defaultProps / TextInput.defaultProps
 * React áp defaultProps TRƯỚC khi truyền vào component, chỉ khi prop bị omit.
 *
 * TẠI SAO không dùng render-patch (cách cũ):
 *   Trên RN 0.86, cả Text lẫn TextInput đều là plain function components
 *   (TextImpl / function TextInput — không phải class). Chúng không có thuộc
 *   tính .render, nên `typeof Comp.render !== "function"` → hàm patch thoát sớm
 *   mà không làm gì cả (silent no-op, không crash).
 *
 * Giới hạn của defaultProps:
 *   Bất kỳ <Text style={...}> nào tự đặt style prop sẽ KHÔNG nhận được
 *   fontFamily này (style của caller thắng hoàn toàn). Những chỗ đó cần tự
 *   khai fontFamily rõ ràng — type.* token trong theme.ts đã bao phủ hầu hết.
 *   <Text> KHÔNG có style prop (hoặc style={undefined}) thì được bao phủ.
 *
 * Lưu ý: defaultProps trên function component bị deprecated từ React 18 (sẽ
 * có console.warn trong dev mode) nhưng vẫn hoạt động đúng trên RN 0.86.
 *
 * Gọi 1 lần ở App.tsx (module-level, trước khi bất kỳ component nào render).
 */
import { Text, TextInput } from "react-native";
import { fonts } from "./theme";

let applied = false;

export function applyGlobalFont() {
  if (applied) return;
  applied = true;

  const defaultStyle = { fontFamily: fonts.regular };

  try {
    (Text as any).defaultProps = {
      ...((Text as any).defaultProps ?? {}),
      style: defaultStyle,
    };
    (TextInput as any).defaultProps = {
      ...((TextInput as any).defaultProps ?? {}),
      style: defaultStyle,
    };
  } catch {
    // Không chặn app nếu môi trường không cho set defaultProps.
  }
}
