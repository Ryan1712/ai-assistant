import React, { useState } from "react";
import { Alert, Text, View } from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useHeaderHeight } from "@react-navigation/elements";
import { useNavigation } from "@react-navigation/native";
import { forgotPassword, resetPassword } from "../../src/api/auth";
import { ErrorText, Field, PrimaryButton } from "../../src/ui/form";
import { colors, fonts, spacing, type } from "../../src/ui/theme";

export default function ForgotPassword() {
  const navigation = useNavigation<any>();
  const headerHeight = useHeaderHeight();
  const [step, setStep] = useState<"email" | "reset">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const sendCode = async () => {
    const e = email.trim();
    if (!e) {
      setError("Nhập email của bạn.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await forgotPassword(e);
      setInfo(`Nếu email này có tài khoản, mã đặt lại đã được gửi tới ${e}. Nhập mã bên dưới.`);
      setStep("reset");
    } catch (err: any) {
      setError(String(err?.message ?? err));
    } finally {
      setBusy(false);
    }
  };

  const submitReset = async () => {
    if (!code.trim()) {
      setError("Nhập mã đặt lại (6 số).");
      return;
    }
    if (password.length < 8) {
      setError("Mật khẩu mới cần ít nhất 8 ký tự.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await resetPassword(email.trim(), code.trim(), password);
      Alert.alert("Đã đặt lại mật khẩu", "Đăng nhập bằng mật khẩu mới nhé.", [
        { text: "OK", onPress: () => navigation.navigate("Login") },
      ]);
    } catch (err: any) {
      setError(
        err?.status === 400
          ? "Mã không đúng hoặc đã hết hạn — bấm “Gửi lại mã” và thử lại."
          : String(err?.message ?? err),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.bg }}
      behavior="padding"
      keyboardVerticalOffset={headerHeight}
    >
      <View style={{ flex: 1, justifyContent: "center", padding: spacing.xl, gap: spacing.md }}>
        <Text style={type.title}>Quên mật khẩu</Text>

        {step === "email" ? (
          <>
            <Text style={{ color: colors.textSecondary }}>
              Nhập email tài khoản — chúng tôi sẽ gửi mã đặt lại mật khẩu (hiệu lực 15 phút).
            </Text>
            <Field
              placeholder="Email"
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
            />
            <ErrorText error={error} />
            <PrimaryButton title="Gửi mã đặt lại" onPress={sendCode} busy={busy} />
          </>
        ) : (
          <>
            {info && <Text style={{ color: colors.textSecondary }}>{info}</Text>}
            <Field
              placeholder="Mã đặt lại (6 số)"
              value={code}
              onChangeText={setCode}
              keyboardType="number-pad"
              autoCapitalize="none"
            />
            <Field
              placeholder="Mật khẩu mới (≥ 8 ký tự)"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />
            <ErrorText error={error} />
            <PrimaryButton title="Đặt lại mật khẩu" onPress={submitReset} busy={busy} />
            <Text
              onPress={() => {
                setStep("email");
                setError(null);
              }}
              style={{ color: colors.primary, fontFamily: fonts.semibold, textAlign: "center" }}
            >
              Gửi lại mã
            </Text>
          </>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}
