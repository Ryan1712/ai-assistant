import React from "react";
import { ActivityIndicator, View } from "react-native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { useAuth } from "../auth/AuthContext";
import { colors } from "../ui/theme";
import { AuthNavigator } from "./AuthNavigator";
import { MainNavigator } from "./MainNavigator";

const Root = createNativeStackNavigator();

/** Cổng auth: đang tải phiên → spinner; có user → app chính; chưa có → luồng đăng nhập.
 * Thay cho Gate + Redirect của expo-router trước đây. */
export function RootNavigator() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg }}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <Root.Navigator screenOptions={{ headerShown: false }}>
      {user ? (
        <Root.Screen name="Main" component={MainNavigator} />
      ) : (
        <Root.Screen name="Auth" component={AuthNavigator} />
      )}
    </Root.Navigator>
  );
}
