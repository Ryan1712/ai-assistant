// Learn more https://docs.expo.dev/guides/customizing-metro/
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
