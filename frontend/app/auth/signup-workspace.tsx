import React from "react";
import { useAuth } from "../../src/auth/AuthContext";
import { ConversationalForm, ConversationalStep } from "../../src/ui/ConversationalForm";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const STEPS: ConversationalStep[] = [
  { key: "workspace_name", prompt: "Công ty của bạn tên là gì?", placeholder: "Tên công ty",
    autoCapitalize: "words",
    validate: (v) => (v.length < 2 ? "Tên công ty hơi ngắn, bạn nhập lại giúp mình nhé." : null) },
  { key: "full_name", prompt: "Bạn tên là gì?", placeholder: "Họ tên",
    autoCapitalize: "words",
    validate: (v) => (v.length < 2 ? "Tên hơi ngắn, bạn nhập lại giúp mình nhé." : null) },
  { key: "email", prompt: "Email bạn dùng để đăng nhập?", placeholder: "Email",
    keyboardType: "email-address",
    validate: (v) => (EMAIL_RE.test(v) ? null : "Email này không đúng định dạng, thử lại nhé.") },
  { key: "password", prompt: "Đặt mật khẩu cho tài khoản (ít nhất 8 ký tự):",
    placeholder: "Mật khẩu", secureTextEntry: true, trim: false,
    validate: (v) => (v.length < 8 ? "Mật khẩu cần ít nhất 8 ký tự, thử lại nhé." : null) },
];

export default function SignupWorkspace() {
  const { signupWorkspace } = useAuth();

  return (
    <ConversationalForm
      intro="Chào bạn! Mình hỏi vài câu để tạo công ty cho bạn nhé."
        steps={STEPS}
        submittingLabel="Đang tạo công ty cho bạn..."
        onComplete={(a) =>
          signupWorkspace({
            workspace_name: a.workspace_name,
            full_name: a.full_name,
            email: a.email,
            password: a.password,
          })
        }
        mapError={(e) =>
          e?.detail === "email_taken" ? "Email này đã được dùng rồi, bạn thử email khác nhé." : String(e?.message ?? e)
        }
        errorStepKey={(e) => (e?.detail === "email_taken" ? "email" : undefined)}
    />
  );
}
