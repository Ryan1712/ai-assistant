import Constants from "expo-constants";
import * as Device from "expo-device";
import { Platform } from "react-native";
import { apiFetch } from "../api/client";
import { getDeviceUuid } from "../auth/tokenStore";

// Expo Go Android (SDK 53+): chính việc import expo-notifications đã throw
// (remote push bị gỡ khỏi Expo Go) → require lười trong hàm, không import tĩnh.
const isExpoGoAndroid =
  Platform.OS === "android" && Constants.executionEnvironment === "storeClient";

/**
 * Đăng ký Expo push token cho device hiện tại — best-effort, không bao giờ throw.
 * Expo Go (Android SDK 53+) không hỗ trợ remote push → bỏ qua ngay từ đầu;
 * môi trường khác nếu lỗi thì chỉ log rồi bỏ qua; app vẫn chạy bình thường.
 */
export async function registerPushTokenBestEffort(): Promise<void> {
  try {
    if (Platform.OS === "web" || !Device.isDevice || isExpoGoAndroid) return;
    const Notifications =
      require("expo-notifications") as typeof import("expo-notifications");
    const perm = await Notifications.requestPermissionsAsync();
    if (!perm.granted) return;
    const projectId: string | undefined = Constants.expoConfig?.extra?.eas?.projectId;
    const { data: token } = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined,
    );
    await apiFetch("/api/v1/devices/push-token", {
      method: "PUT",
      body: { device_uuid: await getDeviceUuid(), push_token: token },
    });
  } catch (e) {
    console.log("Bỏ qua đăng ký push token (môi trường không hỗ trợ remote push):", e);
  }
}
