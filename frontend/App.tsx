import React from "react";
import { ActivityIndicator, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { NavigationContainer } from "@react-navigation/native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";
import {
  useFonts,
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
  Inter_800ExtraBold,
} from "@expo-google-fonts/inter";
import { AuthProvider } from "./src/auth/AuthContext";
import { RootNavigator } from "./src/navigation/RootNavigator";
import { applyGlobalFont } from "./src/ui/globalFont";
import { colors } from "./src/ui/theme";
import { ErrorBoundary } from "./src/errors/ErrorBoundary";
import { initSentry } from "./src/errors/sentry";
import { initGlobalHandlers } from "./src/errors/globalHandlers";
import { initSessionSentinel } from "./src/errors/sessionSentinel";

// Đặt Inter làm font mặc định cho mọi Text/TextInput (chạy 1 lần khi nạp module).
applyGlobalFont();

// Khởi tạo các dịch vụ báo cáo sự cố trước khi bất kỳ component nào được render.
// initSentry: no-op khi thiếu EXPO_PUBLIC_SENTRY_DSN (ADR-003).
// initGlobalHandlers: bắt lỗi JS và promise rejection toàn cục.
// initSessionSentinel: theo dõi trạng thái app (foreground/background).
initSentry().catch(() => {});
initGlobalHandlers();
initSessionSentinel();

export default function App() {
  const [fontsLoaded] = useFonts({
    "Inter-Regular": Inter_400Regular,
    "Inter-Medium": Inter_500Medium,
    "Inter-SemiBold": Inter_600SemiBold,
    "Inter-Bold": Inter_700Bold,
    "Inter-ExtraBold": Inter_800ExtraBold,
  });

  if (!fontsLoaded) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg }}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    // ErrorBoundary nằm ngoài cùng để bắt mọi crash — kể cả crash trong GestureHandler
    <ErrorBoundary>
      <GestureHandlerRootView style={{ flex: 1 }}>
        <SafeAreaProvider>
          <KeyboardProvider>
            <AuthProvider>
              <StatusBar style="dark" />
              <NavigationContainer>
                <RootNavigator />
              </NavigationContainer>
            </AuthProvider>
          </KeyboardProvider>
        </SafeAreaProvider>
      </GestureHandlerRootView>
    </ErrorBoundary>
  );
}
