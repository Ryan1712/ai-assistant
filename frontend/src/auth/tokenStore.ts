import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import AsyncStorage from "@react-native-async-storage/async-storage";

export type Tokens = { access_token: string; refresh_token: string };

const KEY = "ai-assistant.tokens";

// SecureStore không có trên web → fallback AsyncStorage (localStorage)
const isWeb = Platform.OS === "web";

export async function getTokens(): Promise<Tokens | null> {
  const raw = isWeb ? await AsyncStorage.getItem(KEY) : await SecureStore.getItemAsync(KEY);
  return raw ? (JSON.parse(raw) as Tokens) : null;
}

export async function setTokens(tokens: Tokens): Promise<void> {
  const raw = JSON.stringify(tokens);
  if (isWeb) await AsyncStorage.setItem(KEY, raw);
  else await SecureStore.setItemAsync(KEY, raw);
}

export async function clearTokens(): Promise<void> {
  if (isWeb) await AsyncStorage.removeItem(KEY);
  else await SecureStore.deleteItemAsync(KEY);
}

const DEVICE_KEY = "ai-assistant.device-uuid";

export async function getDeviceUuid(): Promise<string> {
  let id = await AsyncStorage.getItem(DEVICE_KEY);
  if (!id) {
    id = `dev-${Math.random().toString(36).slice(2, 10)}-${Date.now().toString(36)}`;
    await AsyncStorage.setItem(DEVICE_KEY, id);
  }
  return id;
}
