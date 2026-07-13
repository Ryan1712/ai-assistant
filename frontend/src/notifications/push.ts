import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { apiFetch } from "../api/client";
import { getDeviceUuid } from "../auth/tokenStore";

/**
 * Đăng ký Expo push token cho device hiện tại — best-effort, không bao giờ throw.
 * Expo Go (Android SDK 53+) không hỗ trợ remote push → getExpoPushTokenAsync
 * sẽ lỗi và ta chỉ log rồi bỏ qua; app vẫn chạy bình thường.
 */
export async function registerPushTokenBestEffort(): Promise<void> {
  try {
    if (Platform.OS === "web" || !Device.isDevice) return; // web/giả lập: không có remote push
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
    console.log("Bỏ qua đăng ký push token (Expo Go không hỗ trợ remote push):", e);
  }
}
