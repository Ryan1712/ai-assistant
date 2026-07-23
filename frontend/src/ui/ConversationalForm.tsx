import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { colors, radius, spacing, type } from "./theme";

export type ConversationalStep = {
  key: string;
  prompt: string;
  placeholder?: string;
  secureTextEntry?: boolean;
  keyboardType?: "default" | "email-address";
  autoCapitalize?: "none" | "sentences" | "words" | "characters";
  trim?: boolean; // mặc định true, tắt cho password
  validate?: (value: string, answers: Record<string, string>) => string | null;
};

type Row =
  | { key: string; kind: "bot" | "user" | "error"; text: string };

export function ConversationalForm({
  intro,
  steps,
  onComplete,
  mapError,
  errorStepKey,
  submittingLabel = "Đang xử lý...",
}: {
  intro?: string;
  steps: ConversationalStep[];
  onComplete: (answers: Record<string, string>) => Promise<void>;
  mapError: (e: any) => string;
  errorStepKey?: (e: any) => string | undefined;
  submittingLabel?: string;
}) {
  const [rows, setRows] = useState<Row[]>([]);
  const [stepIndex, setStepIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<FlatList>(null);

  useEffect(() => {
    const seed: Row[] = [];
    if (intro) seed.push({ key: "intro", kind: "bot", text: intro });
    if (steps[0]) seed.push({ key: `q-${steps[0].key}`, kind: "bot", text: steps[0].prompt });
    setRows(seed);
  }, []);

  const step = steps[stepIndex];
  const done = stepIndex >= steps.length;

  const rewindTo = (key: string) => {
    const idx = steps.findIndex((s) => s.key === key);
    if (idx === -1) return;
    setStepIndex(idx);
    setRows((prev) => [...prev, { key: `retry-${key}-${prev.length}`, kind: "bot", text: steps[idx].prompt }]);
  };

  const submitStep = async () => {
    if (!step || busy) return;
    const raw = step.trim === false ? input : input.trim();
    if (!raw) return;
    const err = step.validate?.(raw, answers);
    if (err) {
      setRows((prev) => [...prev, { key: `err-${prev.length}`, kind: "error", text: err }]);
      return;
    }
    const displayText = step.secureTextEntry ? "•".repeat(Math.min(raw.length, 12)) : raw;
    const nextAnswers = { ...answers, [step.key]: raw };
    setAnswers(nextAnswers);
    setInput("");
    const nextIndex = stepIndex + 1;
    // Key theo prev.length (không phải step.key) — 1 step có thể được trả lời lại
    // nhiều lần sau khi rewindTo() do lỗi, step.key lặp lại sẽ đụng key cũ.
    setRows((prev) => {
      const rows: Row[] = [{ key: `a-${prev.length}`, kind: "user", text: displayText }];
      if (steps[nextIndex]) {
        rows.push({ key: `q-${prev.length + 1}`, kind: "bot", text: steps[nextIndex].prompt });
      }
      return [...prev, ...rows];
    });
    setStepIndex(nextIndex);

    if (nextIndex >= steps.length) {
      setBusy(true);
      setRows((prev) => [...prev, { key: `submitting-${prev.length}`, kind: "bot", text: submittingLabel }]);
      try {
        await onComplete(nextAnswers);
      } catch (e: any) {
        const msg = mapError(e);
        setRows((prev) => [...prev, { key: `fail-${prev.length}`, kind: "error", text: msg }]);
        const back = errorStepKey?.(e);
        if (back) rewindTo(back);
        else rewindTo(steps[steps.length - 1].key);
      } finally {
        setBusy(false);
      }
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.bg }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <FlatList
        ref={listRef}
        data={rows}
        keyExtractor={(r) => r.key}
        contentContainerStyle={{ padding: spacing.md, gap: spacing.sm }}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        renderItem={({ item }) => (
          <View
            style={[
              {
                borderRadius: radius.lg,
                padding: spacing.md,
                maxWidth: "85%",
              },
              item.kind === "user"
                ? { backgroundColor: colors.primary, alignSelf: "flex-end" }
                : item.kind === "error"
                  ? { backgroundColor: colors.dangerBg, alignSelf: "center" }
                  : { backgroundColor: colors.surfaceAlt, alignSelf: "flex-start" },
            ]}
          >
            <Text style={{ color: item.kind === "user" ? colors.onPrimary : colors.text }}>
              {item.text}
            </Text>
          </View>
        )}
      />
      {!done && (
        <View
          style={{
            flexDirection: "row",
            alignItems: "flex-end",
            padding: spacing.md,
            gap: spacing.sm,
            borderTopWidth: 1,
            borderColor: colors.border,
            backgroundColor: colors.surface,
          }}
        >
          <TextInput
            style={{
              flex: 1,
              borderWidth: 1,
              borderColor: colors.borderStrong,
              borderRadius: radius.md,
              paddingHorizontal: spacing.md,
              paddingVertical: spacing.sm,
              fontSize: type.body.fontSize,
              color: colors.text,
            }}
            placeholder={step?.placeholder}
            placeholderTextColor={colors.textMuted}
            value={input}
            onChangeText={setInput}
            onSubmitEditing={submitStep}
            secureTextEntry={step?.secureTextEntry}
            keyboardType={step?.keyboardType}
            autoCapitalize={step?.autoCapitalize ?? "none"}
            editable={!busy}
          />
          <TouchableOpacity
            style={{
              backgroundColor: colors.primary,
              borderRadius: radius.md,
              paddingHorizontal: spacing.lg,
              paddingVertical: spacing.md,
            }}
            onPress={submitStep}
            disabled={busy}
          >
            {busy ? (
              <ActivityIndicator color={colors.onPrimary} />
            ) : (
              <Text style={{ color: colors.onPrimary, fontWeight: "700" }}>Gửi</Text>
            )}
          </TouchableOpacity>
        </View>
      )}
    </KeyboardAvoidingView>
  );
}
