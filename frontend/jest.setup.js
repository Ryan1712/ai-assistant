// jest.setup.js — mock toàn cục cho Jest / React Native test environment
// Owner: google-qa-engineer (Task 1.S)
// Chạy sau khi Jest framework khởi động (setupFilesAfterEnv)

// ─── Bật act() environment cho React 19 ──────────────────────────────────────
// Thiếu cờ này, React 19 báo "current testing environment is not configured to
// support act(...)" và KHÔNG gom được các cập nhật bất đồng bộ. Hậu quả cụ thể
// đã gặp: FlatList/VirtualizedList hẹn setState qua setTimeout, timer bắn SAU khi
// test kết thúc → cây React của test trước rò sang test sau → mọi test phía sau
// render hỏng. Đây là cấu hình môi trường, không phải nới lỏng kiểm thử.
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// ─── Mock @react-native-async-storage/async-storage ─────────────────────────
// Dùng mock chính chủ của package (đúng API, track calls trong test)
jest.mock(
  "@react-native-async-storage/async-storage",
  () => require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);

// ─── Mock expo-device ────────────────────────────────────────────────────────
// expo-device không chạy được trong Jest (cần native module)
jest.mock("expo-device", () => ({
  isDevice: false,
  brand: "Apple",
  manufacturer: "Apple",
  modelName: "iPhone Simulator",
  modelId: "x86_64",
  designName: null,
  productName: null,
  deviceYearClass: 2022,
  totalMemory: null,
  supportedCpuArchitectures: null,
  osName: "iOS",
  osVersion: "17.0",
  osBuildId: "21A329",
  osInternalBuildId: "21A329",
  osBuildFingerprint: null,
  platformApiLevel: null,
  deviceName: "iPhone Simulator",
  DeviceType: {
    UNKNOWN: 0,
    PHONE: 1,
    TABLET: 2,
    DESKTOP: 3,
    TV: 4,
  },
  getDeviceTypeAsync: jest.fn(() => Promise.resolve(1)),
  getUptimeAsync: jest.fn(() => Promise.resolve(0)),
  isRootedExperimentalAsync: jest.fn(() => Promise.resolve(false)),
  isSideLoadingEnabledAsync: jest.fn(() => Promise.resolve(false)),
  getPlatformFeaturesAsync: jest.fn(() => Promise.resolve([])),
  hasPlatformFeatureAsync: jest.fn(() => Promise.resolve(false)),
}));

// ─── Mock expo-constants ─────────────────────────────────────────────────────
// expo-constants cần native env — mock giá trị tối thiểu cho test
jest.mock("expo-constants", () => ({
  __esModule: true,
  default: {
    expoConfig: {
      version: "1.0.0",
      name: "ai-assistant-test",
      slug: "ai-assistant",
      extra: {},
    },
    appOwnership: null,
    debugMode: false,
    deviceName: "Test Device",
    executionEnvironment: "storeClient",
    experienceUrl: "exp://localhost",
    isHeadless: false,
    linkingUri: "exp://localhost",
    manifest: null,
    sessionId: "test-session-id",
    statusBarHeight: 44,
    systemFonts: [],
    systemVersion: "17.0",
  },
}));

// ─── Mock global fetch ───────────────────────────────────────────────────────
// Các test đặt mock riêng bằng jest.fn() — đây chỉ là sentinel mặc định
global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve({}),
    text: () => Promise.resolve(""),
    statusText: "OK",
  }),
);

// ─── Tắt tiếng console.error của React (bẫy lỗi test ErrorBoundary) ────────
// Sẽ được restore trong từng test file cụ thể khi cần
// (không tắt ở đây toàn cục để không che giấu lỗi thật)
