// jest.config.js — cấu hình Jest cho React Native 0.86 + Expo SDK 57
// Owner: google-qa-engineer (Task 1.S)

/** @type {import('jest-expo').JestPreset} */
module.exports = {
  preset: "jest-expo",

  // Tự động gọi jest.clearAllMocks() trước mỗi test — ngăn global.fetch.mock.calls
  // tích lũy qua các test (fix "flush() không làm gì khi hàng đợi rỗng").
  clearMocks: true,

  // Setup file chạy sau khi Jest framework khởi động (testing-library cleanup etc.)
  setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],

  // transformIgnorePatterns: cần đủ rộng để babel transform các package RN chưa pre-compile
  // Thêm mọi package native cần transform: @react-navigation, @sentry, expo-*, react-native-*
  transformIgnorePatterns: [
    "node_modules/(?!(" +
      "react-native|" +
      "@react-native|" +
      "@react-native-community|" +
      "@react-navigation|" +
      "expo|" +
      "expo-device|" +
      "expo-constants|" +
      "expo-modules-core|" +
      "expo-secure-store|" +
      "expo-font|" +
      "expo-linking|" +
      "expo-status-bar|" +
      "expo-file-system|" +
      "expo-audio|" +
      "expo-notifications|" +
      "expo-document-picker|" +
      "expo-sharing|" +
      "expo-speech-recognition|" +
      "@expo|" +
      "@expo/vector-icons|" +
      "@expo-google-fonts|" +
      "@sentry|" +
      "react-native-gesture-handler|" +
      "react-native-screens|" +
      "react-native-safe-area-context|" +
      "react-native-keyboard-controller|" +
      "react-native-markdown-display|" +
      "react-native-web|" +
      "@react-native-async-storage" +
    ")/)",
  ],

  // Chỉ lấy test file trong __tests__/ với đuôi .ts / .tsx
  testMatch: [
    "**/__tests__/**/*.[jt]s?(x)",
    "**/?(*.)+(spec|test).[jt]s?(x)",
  ],

  // Thư mục root của test là frontend/
  roots: ["<rootDir>"],

  // Bỏ qua node_modules trừ các package được transform ở trên
  testPathIgnorePatterns: ["/node_modules/", "/android/", "/ios/"],

  // Coverage (mặc định tắt — bật bằng --coverage flag)
  collectCoverageFrom: [
    "src/**/*.{ts,tsx}",
    "app/**/*.{ts,tsx}",
    "!src/**/*.d.ts",
    "!**/node_modules/**",
  ],
};
