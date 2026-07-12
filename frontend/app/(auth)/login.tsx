import React, { useState } from "react";
import { Text, View } from "react-native";
import { Link, Stack } from "expo-router";
import { useAuth } from "../../src/auth/AuthContext";
import { ErrorText, Field, PrimaryButton } from "../../src/ui/form";

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
    <View style={{ flex: 1, justifyContent: "center", padding: 24, backgroundColor: "#f9fafb" }}>
      <Stack.Screen options={{ title: "Đăng nhập" }} />
      <Text style={{ fontSize: 28, fontWeight: "700", marginBottom: 24 }}>Trợ lý AI</Text>
      <Field placeholder="Email" value={email} onChangeText={setEmail}
             keyboardType="email-address" />
      <Field placeholder="Mật khẩu" value={password} onChangeText={setPassword} secureTextEntry />
      <ErrorText error={error} />
      <PrimaryButton title="Đăng nhập" onPress={submit} busy={busy} />
      <View style={{ marginTop: 20, gap: 8 }}>
        <Link href="/(auth)/signup-code" style={{ color: "#2563eb" }}>
          Nhân viên mới? Đăng ký bằng mã mời công ty
        </Link>
        <Link href="/(auth)/signup-workspace" style={{ color: "#2563eb" }}>
          Tạo công ty mới (CEO)
        </Link>
      </View>
    </View>
  );
}
