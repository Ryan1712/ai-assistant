import React, { useEffect, useRef, useState } from "react";
import { TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors } from "../ui/theme";

// Native module (iOS SFSpeechRecognizer / Web Speech API) — thiếu trong Expo Go
// hoặc trình duyệt không hỗ trợ thì require throw / isRecognitionAvailable false
// → nút tự ẩn, app không crash (cùng pattern guard push notification).
let Speech: typeof import("expo-speech-recognition") | null = null;
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  Speech = require("expo-speech-recognition");
} catch {}

export function DictationButton({ onText }: { onText: (text: string) => void }) {
  const [available, setAvailable] = useState(false);
  const [listening, setListening] = useState(false);
  const subs = useRef<{ remove: () => void }[]>([]);

  useEffect(() => {
    if (!Speech) return;
    try {
      setAvailable(Speech.ExpoSpeechRecognitionModule.isRecognitionAvailable());
    } catch {}
    return () => {
      subs.current.forEach((s) => s.remove());
      subs.current = [];
    };
  }, []);

  if (!available) return null;

  const stop = () => {
    try {
      Speech!.ExpoSpeechRecognitionModule.stop();
    } catch {}
    setListening(false);
  };

  const start = async () => {
    try {
      const perm = await Speech!.ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!perm.granted) return;
      subs.current.forEach((s) => s.remove());
      subs.current = [
        Speech!.ExpoSpeechRecognitionModule.addListener("result", (e) => {
          const t = e.results?.[0]?.transcript;
          if (t) onText(t);
        }),
        Speech!.ExpoSpeechRecognitionModule.addListener("end", () => setListening(false)),
        Speech!.ExpoSpeechRecognitionModule.addListener("error", () => setListening(false)),
      ];
      Speech!.ExpoSpeechRecognitionModule.start({ lang: "vi-VN", interimResults: true });
      setListening(true);
    } catch {
      setListening(false);
    }
  };

  return (
    <TouchableOpacity
      onPress={listening ? stop : start}
      style={{ width: 36, height: 36, alignItems: "center", justifyContent: "center" }}
      accessibilityLabel={listening ? "Dừng nói" : "Nói với trợ lý"}
      hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
    >
      <Ionicons name={listening ? "mic" : "mic-outline"} size={22} color={listening ? colors.danger : colors.textSecondary} />
    </TouchableOpacity>
  );
}
