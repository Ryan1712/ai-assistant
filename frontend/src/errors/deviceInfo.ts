/**
 * deviceInfo.ts — thu thập thông tin thiết bị và app cho crash payload.
 * Sử dụng expo-device và expo-constants (đã được mock trong môi trường test).
 */

import Constants from "expo-constants";
import { Platform } from "react-native";
import * as Device from "expo-device";

/** Thông tin thiết bị và app */
export interface DeviceInfo {
  app_version: string;
  build_number: string;
  platform: string;
  os_version: string;
  device_model: string;
  is_device: boolean;
}

/**
 * Lấy thông tin thiết bị và app.
 * An toàn: không bao giờ ném lỗi — trả về giá trị mặc định nếu không đọc được.
 */
export function getDeviceInfo(): DeviceInfo {
  try {
    const config = Constants.expoConfig ?? {};
    const iosConfig = (config as { ios?: { buildNumber?: string } }).ios;
    const androidConfig = (config as { android?: { versionCode?: number } }).android;

    return {
      app_version: (config as { version?: string }).version ?? "unknown",
      build_number:
        iosConfig?.buildNumber ??
        String(androidConfig?.versionCode ?? "0"),
      platform: Platform.OS,
      os_version: Device.osVersion ?? "unknown",
      device_model: Device.modelName ?? "unknown",
      is_device: Device.isDevice ?? false,
    };
  } catch {
    // Không ném lỗi — trả về giá trị dự phòng
    return {
      app_version: "unknown",
      build_number: "0",
      platform: Platform.OS,
      os_version: "unknown",
      device_model: "unknown",
      is_device: false,
    };
  }
}
