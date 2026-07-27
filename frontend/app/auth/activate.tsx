// Màn hình kích hoạt tài khoản CEO tạo trước (create_employee cũ) — tắt hẳn
// (2026-07-26, chỉ CEO đăng nhập app; nhân viên là record chỉ-tên qua
// add_employee, không còn ai kích hoạt). Route BE /auth/activate đã comment out
// (app/api/auth.py) và AuthContext.activateAccount() cũng đã comment out
// (src/auth/AuthContext.tsx). Màn này đã bỏ khỏi AuthNavigator từ trước — comment
// out thân component thay vì xóa file, cùng quy ước với các luồng đã tắt khác.
//
// import React from "react";
// import { useAuth } from "../../src/auth/AuthContext";
// import { ConversationalForm, ConversationalStep } from "../../src/ui/ConversationalForm";
//
// const STEPS: ConversationalStep[] = [
//   { key: "code", prompt: "Sếp/quản lý đã cho bạn mã kích hoạt chưa? Nhập giúp mình nhé (8 ký tự).",
//     placeholder: "Mã kích hoạt", autoCapitalize: "characters",
//     validate: (v) => (v.length < 4 ? "Mã có vẻ chưa đúng, thử lại nhé." : null) },
//   { key: "password", prompt: "Đặt mật khẩu cho tài khoản (ít nhất 8 ký tự):",
//     placeholder: "Mật khẩu", secureTextEntry: true, trim: false,
//     validate: (v) => (v.length < 8 ? "Mật khẩu cần ít nhất 8 ký tự, thử lại nhé." : null) },
// ];
//
// const ERROR_MAP: Record<string, string> = {
//   invalid_code: "Mã kích hoạt không đúng hoặc đã hết hạn, bạn kiểm tra lại giúp mình nhé.",
// };
//
// export default function Activate() {
//   const { activateAccount } = useAuth();
//
//   return (
//     <ConversationalForm
//       intro="Tài khoản của bạn đã được tạo sẵn — chỉ cần nhập mã kích hoạt và đặt mật khẩu là xong."
//       steps={STEPS}
//       submittingLabel="Đang kích hoạt tài khoản..."
//       onComplete={(a) =>
//         activateAccount({ code: a.code.toUpperCase(), password: a.password })
//       }
//       mapError={(e) => ERROR_MAP[e?.detail as string] ?? String(e?.message ?? e)}
//       errorStepKey={(e) => (e?.detail === "invalid_code" ? "code" : undefined)}
//     />
//   );
// }
