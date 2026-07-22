import React from "react";
import { useAuth } from "../../src/auth/AuthContext";
import { ConversationalForm, ConversationalStep } from "../../src/ui/ConversationalForm";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const STEPS: ConversationalStep[] = [
  { key: "invite_code", prompt: "Bạn có mã mời của công ty chưa? Nhập giúp mình nhé (8 ký tự).",
    placeholder: "Mã mời", autoCapitalize: "characters",
    validate: (v) => (v.length < 4 ? "Mã mời có vẻ chưa đúng, thử lại nhé." : null) },
  { key: "full_name", prompt: "Bạn tên là gì?", placeholder: "Họ tên", autoCapitalize: "words",
    validate: (v) => (v.length < 2 ? "Tên hơi ngắn, bạn nhập lại giúp mình nhé." : null) },
  { key: "email", prompt: "Email bạn dùng để đăng nhập?", placeholder: "Email",
    keyboardType: "email-address",
    validate: (v) => (EMAIL_RE.test(v) ? null : "Email này không đúng định dạng, thử lại nhé.") },
  { key: "password", prompt: "Đặt mật khẩu cho tài khoản (ít nhất 8 ký tự):",
    placeholder: "Mật khẩu", secureTextEntry: true, trim: false,
    validate: (v) => (v.length < 8 ? "Mật khẩu cần ít nhất 8 ký tự, thử lại nhé." : null) },
];

const ERROR_MAP: Record<string, string> = {
  invalid_invite_code: "Mã mời không đúng, bạn kiểm tra lại giúp mình nhé.",
  email_taken: "Email này đã được dùng rồi, bạn thử email khác nhé.",
  plan_limit_reached: "Công ty đã đạt giới hạn thành viên của gói hiện tại.",
};

export default function SignupCode() {
  const { signupCode } = useAuth();

  return (
    <ConversationalForm
      intro="Chào bạn! Mình hỏi vài câu để đưa bạn vào đúng công ty nhé."
        steps={STEPS}
        submittingLabel="Đang tạo tài khoản cho bạn..."
        onComplete={(a) =>
          signupCode({
            invite_code: a.invite_code.toUpperCase(),
            full_name: a.full_name,
            email: a.email,
            password: a.password,
          })
        }
        mapError={(e) => ERROR_MAP[e?.detail as string] ?? String(e?.message ?? e)}
        errorStepKey={(e) => {
          if (e?.detail === "invalid_invite_code") return "invite_code";
          if (e?.detail === "email_taken") return "email";
          return undefined;
        }}
    />
  );
}
