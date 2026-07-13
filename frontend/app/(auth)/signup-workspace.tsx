import React, { useState } from "react";
import { View } from "react-native";
import { Stack } from "expo-router";
import { useAuth } from "../../src/auth/AuthContext";
import { ErrorText, Field, PrimaryButton } from "../../src/ui/form";
import { colors, spacing } from "../../src/ui/theme";

export default function SignupWorkspace() {
  const { signupWorkspace } = useAuth();
  const [workspaceName, setWorkspaceName] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await signupWorkspace({
        workspace_name: workspaceName.trim(),
        full_name: fullName.trim(),
        email: email.trim(),
        password,
      });
    } catch (e: any) {
      setError(e?.detail === "email_taken" ? "Email đã được sử dụng." : String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View
      style={{ flex: 1, justifyContent: "center", padding: spacing.xl, backgroundColor: colors.bg }}
    >
      <Stack.Screen options={{ title: "Tạo công ty mới" }} />
      <Field placeholder="Tên công ty" value={workspaceName} onChangeText={setWorkspaceName}
             autoCapitalize="words" />
      <Field placeholder="Họ tên của bạn (CEO)" value={fullName} onChangeText={setFullName}
             autoCapitalize="words" />
      <Field placeholder="Email" value={email} onChangeText={setEmail}
             keyboardType="email-address" />
      <Field placeholder="Mật khẩu (≥8 ký tự)" value={password} onChangeText={setPassword}
             secureTextEntry />
      <ErrorText error={error} />
      <PrimaryButton title="Tạo công ty & bắt đầu" onPress={submit} busy={busy} />
    </View>
  );
}
