import React, { useState } from "react";
import { Image, Keyboard, Text, TouchableWithoutFeedback, View } from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useNavigation } from "@react-navigation/native";
import { useAuth } from "../../src/auth/AuthContext";
import { ErrorText, Field, PrimaryButton } from "../../src/ui/form";
import { colors, fonts, radius, shadow, spacing } from "../../src/ui/theme";

// Regex email "đủ dùng" phía client — chỉ chặn input rõ ràng sai (thiếu @ / thiếu
// tên miền), không tham vọng đúng RFC. Server vẫn là nơi xác thực thật sự.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Login() {
  const { login } = useAuth();
  const navigation = useNavigation<any>();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    Keyboard.dismiss();
    // Validate phía client TRƯỚC — không gọi BE khi input rõ ràng sai, và không
    // phơi message dài/kỹ thuật từ BE ra người dùng.
    const em = email.trim();
    if (!EMAIL_RE.test(em)) {
      setError("Email không hợp lệ.");
      return;
    }
    if (!password) {
      setError("Vui lòng nhập mật khẩu.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(em, password);
    } catch {
      // Gộp mọi lỗi đăng nhập từ BE về 1 message ngắn, thân thiện — không lộ chi
      // tiết (sai email vs sai mật khẩu vs account_pending) ra ngoài.
      setError("Tên đăng nhập hoặc mật khẩu không đúng.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: colors.bg }} behavior="padding">
      {/* Chạm ra ngoài input → ẩn bàn phím (RN không tự blur khi tap chỗ trống). */}
      <TouchableWithoutFeedback onPress={Keyboard.dismiss} accessible={false}>
        <View style={{ flex: 1, justifyContent: "center", padding: spacing.xl }}>
          <View style={{ alignItems: "center", marginBottom: spacing.xxl }}>
            <View
              style={{
                width: 96,
                height: 96,
                borderRadius: radius.xl,
                backgroundColor: colors.surface,
                overflow: "hidden",
                ...shadow.soft,
              }}
            >
              <Image
                source={require("../../assets/logo-icon.png")}
                style={{ width: 96, height: 96 }}
                resizeMode="contain"
              />
            </View>
          </View>

          <Field
            placeholder="Email"
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoComplete="email"
            returnKeyType="next"
          />
          <Field
            placeholder="Mật khẩu"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            returnKeyType="done"
            onSubmitEditing={submit}
          />
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
              onPress={() => navigation.navigate("SignupWorkspace")}
            >
              Tạo công ty mới (CEO)
            </Text>
          </View>
        </View>
      </TouchableWithoutFeedback>
    </KeyboardAvoidingView>
  );
}
