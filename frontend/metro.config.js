// Learn more https://docs.expo.dev/guides/customizing-metro/

// Du an da chuyen han tu expo-router sang React Navigation thu cong (xem
// App.tsx/src/navigation/*), nhung expo-router van con la dependency bac coa
// cua goi expo/@expo/cli nen Metro tu dong bat che do "expo-router mode" khi
// thay thu muc app/ - can tat check nay truoc khi getDefaultConfig() chay,
// neu khong bundle fail voi loi "expo-router is no longer compatible with
// react-navigation" (SDK 56+).
process.env.EXPO_ROUTER_DISABLE_RN_NAVIGATION_CHECK = '1';

const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// markdown-it@10 (dùng bởi react-native-markdown-display) require('punycode') —
// module Node core không có trong React Native runtime. Alias sang package
// userland `punycode` để bundle iOS/Android chạy được.
config.resolver.extraNodeModules = {
  ...(config.resolver.extraNodeModules || {}),
  punycode: require.resolve('punycode/'),
};

module.exports = config;
