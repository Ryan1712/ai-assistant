import React, { useState } from "react";
import { View } from "react-native";
import { Stack } from "expo-router";
import { useAuth } from "../../src/auth/AuthContext";
import { ErrorText, Field, PrimaryButton } from "../../src/ui/form";
import { colors, spacing } from "../../src/ui/theme";

export default function SignupCode() {
  const { signupCode } = useAuth();
  const [inviteCode, setInviteCode] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await signupCode({
        invite_code: inviteCode.trim().toUpperCase(),
        full_name: fullName.trim(),
        email: email.trim(),
        password,
      });
    } catch (e: any) {
      const map: Record<string, string> = {
        invalid_invite_code: "Mã mời không đúng.",
        email_taken: "Email đã được sử dụng.",
        plan_limit_reached: "Công ty đã đạt giới hạn thành viên của gói hiện tại.",
      };
      setError(map[e?.detail as string] ?? String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View
      style={{ flex: 1, justifyContent: "center", padding: spacing.xl, backgroundColor: colors.bg }}
    >
      <Stack.Screen options={{ title: "Đăng ký bằng mã mời" }} />
      <Field placeholder="Mã mời công ty (8 ký tự)" value={inviteCode}
             onChangeText={setInviteCode} autoCapitalize="characters" />
      <Field placeholder="Họ tên" value={fullName} onChangeText={setFullName}
             autoCapitalize="words" />
      <Field placeholder="Email" value={email} onChangeText={setEmail}
             keyboardType="email-address" />
      <Field placeholder="Mật khẩu (≥8 ký tự)" value={password} onChangeText={setPassword}
             secureTextEntry />
      <ErrorText error={error} />
      <PrimaryButton title="Đăng ký" onPress={submit} busy={busy} />
    </View>
  );
}
