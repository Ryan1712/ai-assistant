import React, { useState } from "react";
import { Text, View } from "react-native";
import { Link, Stack } from "expo-router";
import { useAuth } from "../../src/auth/AuthContext";
import { ErrorText, Field, PrimaryButton } from "../../src/ui/form";
import { colors, spacing, type } from "../../src/ui/theme";

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
    } catch (e: any) {
      setError(e?.status === 401 ? "Email hoặc mật khẩu không đúng." : String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View
      style={{ flex: 1, justifyContent: "center", padding: spacing.xl, backgroundColor: colors.bg }}
    >
      <Stack.Screen options={{ title: "Đăng nhập" }} />
      <Text style={[type.title, { marginBottom: spacing.xl }]}>Trợ lý AI</Text>
      <Field placeholder="Email" value={email} onChangeText={setEmail}
             keyboardType="email-address" />
      <Field placeholder="Mật khẩu" value={password} onChangeText={setPassword} secureTextEntry />
      <ErrorText error={error} />
      <PrimaryButton title="Đăng nhập" onPress={submit} busy={busy} />
      <View style={{ marginTop: spacing.xl, gap: spacing.sm }}>
        <Link href="/(auth)/signup-code" style={{ color: colors.primary }}>
          Nhân viên mới? Đăng ký bằng mã mời công ty
        </Link>
        <Link href="/(auth)/signup-workspace" style={{ color: colors.primary }}>
          Tạo công ty mới (CEO)
        </Link>
      </View>
    </View>
  );
}
