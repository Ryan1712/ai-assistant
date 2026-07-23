import { apiFetch } from "./client";

// Quên mật khẩu (OTP qua email). Không cần token — gọi trước khi đăng nhập.
export const forgotPassword = (email: string) =>
  apiFetch<{ status: string }>("/api/v1/auth/forgot-password", {
    method: "POST",
    body: { email },
  });

export const resetPassword = (email: string, code: string, newPassword: string) =>
  apiFetch<void>("/api/v1/auth/reset-password", {
    method: "POST",
    body: { email, code, new_password: newPassword },
  });
