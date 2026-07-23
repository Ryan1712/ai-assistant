import React, { useState } from "react";
import { Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { useAuth } from "../../src/auth/AuthContext";
import { ErrorText, Field, PrimaryButton } from "../../src/ui/form";
import { colors, fonts, spacing, type } from "../../src/ui/theme";

export default function Login() {
  const { login } = useAuth();
  const navigation = useNavigation<any>();
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
      if (e?.detail === "account_pending") {
        setError("Tài khoản chưa kích hoạt — bạn cần nhập mã kích hoạt trước khi đăng nhập.");
      } else if (e?.status === 401) {
        setError("Email hoặc mật khẩu không đúng.");
      } else {
        setError(String(e?.message ?? e));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <View
      style={{ flex: 1, justifyContent: "center", padding: spacing.xl, backgroundColor: colors.bg }}
    >
      <Text style={[type.title, { marginBottom: spacing.xl }]}>Trợ lý AI</Text>
      <Field placeholder="Email" value={email} onChangeText={setEmail}
             keyboardType="email-address" />
      <Field placeholder="Mật khẩu" value={password} onChangeText={setPassword} secureTextEntry />
      <ErrorText error={error} />
      <PrimaryButton title="Đăng nhập" onPress={submit} busy={busy} />
      <Text
        style={{ color: colors.primary, fontFamily: fonts.semibold, marginTop: spacing.md }}
        onPress={() => navigation.navigate("ForgotPassword")}
      >
        Quên mật khẩu?
      </Text>
      <View style={{ marginTop: spacing.xl, gap: spacing.md }}>
        <Text
          style={{ color: colors.primary, fontFamily: fonts.semibold }}
          onPress={() => navigation.navigate("SignupCode")}
        >
          Nhân viên mới? Đăng ký bằng mã mời công ty
        </Text>
        <Text
          style={{ color: colors.primary, fontFamily: fonts.semibold }}
          onPress={() => navigation.navigate("Activate")}
        >
          Đã được thêm vào công ty? Kích hoạt tài khoản
        </Text>
        <Text
          style={{ color: colors.primary, fontFamily: fonts.semibold }}
          onPress={() => navigation.navigate("SignupWorkspace")}
        >
          Tạo công ty mới (CEO)
        </Text>
      </View>
    </View>
  );
}
