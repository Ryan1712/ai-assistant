import React from "react";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { colors, fonts } from "../ui/theme";
import type { AuthStackParamList } from "./types";
import Login from "../../app/auth/login";
import ForgotPassword from "../../app/auth/forgot-password";
import SignupCode from "../../app/auth/signup-code";
import SignupWorkspace from "../../app/auth/signup-workspace";

const Stack = createNativeStackNavigator<AuthStackParamList>();

export function AuthNavigator() {
  return (
    <Stack.Navigator
      screenOptions={{
        animation: "slide_from_right", // iOS slide trái→phải
        headerStyle: { backgroundColor: colors.surface },
        headerShadowVisible: false,
        headerTintColor: colors.primary,
        headerTitleAlign: "center",
        headerTitleStyle: { fontFamily: fonts.bold, fontSize: 17, color: colors.text },
      }}
    >
      <Stack.Screen name="Login" component={Login} options={{ title: "Đăng nhập" }} />
      <Stack.Screen name="ForgotPassword" component={ForgotPassword} options={{ title: "Quên mật khẩu" }} />
      <Stack.Screen name="SignupCode" component={SignupCode} options={{ title: "Đăng ký bằng mã mời" }} />
      <Stack.Screen name="SignupWorkspace" component={SignupWorkspace} options={{ title: "Tạo công ty mới" }} />
    </Stack.Navigator>
  );
}
