import React, { useEffect, useRef, useState } from "react";
import { Text, TouchableOpacity } from "react-native";
import { spacing } from "../ui/theme";

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
      style={{ paddingHorizontal: spacing.sm, paddingVertical: spacing.sm }}
      accessibilityLabel={listening ? "Dừng nói" : "Nói với trợ lý"}
    >
      <Text style={{ fontSize: 20 }}>{listening ? "🔴" : "🎙️"}</Text>
    </TouchableOpacity>
  );
}
