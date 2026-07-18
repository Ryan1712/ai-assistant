import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import { VoiceNote, listVoiceNotes, voiceNoteAudioSource } from "../../src/api/voice";
import { Field, ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

function todayIso(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function VoiceNoteRow({
  note,
  isCurrent,
  playing,
  onToggle,
}: {
  note: VoiceNote;
  isCurrent: boolean;
  playing: boolean;
  onToggle: () => void;
}) {
  const router = useRouter();
  return (
    <View style={styles.row}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <TouchableOpacity
          style={styles.playBtn}
          onPress={onToggle}
          accessibilityLabel={isCurrent && playing ? "Tạm dừng" : "Phát"}
        >
          <Text style={{ color: colors.onPrimary, fontWeight: "700" }}>
            {isCurrent && playing ? "⏸" : "▶"}
          </Text>
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={{ fontWeight: "600", color: colors.text }}>
            {new Date(note.created_at).toLocaleString("vi-VN")}
          </Text>
          {note.tags.length > 0 && (
            <Text style={styles.meta}>{note.tags.map((t) => `#${t}`).join(" · ")}</Text>
          )}
        </View>
      </View>
      <Text style={{ color: colors.text }}>{note.transcript || "(chưa có transcript)"}</Text>
      {note.task_id && (
        <TouchableOpacity onPress={() => router.push(`/tasks/${note.task_id}`)}>
          <Text style={{ color: colors.primary, fontWeight: "700" }}>Xem task liên quan →</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

export default function VoiceNotesScreen() {
  const router = useRouter();
  const [filter, setFilter] = useState<"today" | "all">("all");
  const [tagInput, setTagInput] = useState("");
  const [tagFilter, setTagFilter] = useState<string | undefined>(undefined);
  const [notes, setNotes] = useState<VoiceNote[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);

  const player = useAudioPlayer(null);
  const status = useAudioPlayerStatus(player);

  const load = useCallback(() => {
    setError(null);
    setNotes(null);
    listVoiceNotes(filter === "today" ? todayIso() : undefined, tagFilter)
      .then(setNotes)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, [filter, tagFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const handleFilterTag = () => {
    setTagFilter(tagInput.trim() || undefined);
  };

  const toggle = async (note: VoiceNote) => {
    if (playingId === note.id) {
      if (status.playing) player.pause();
      else player.play();
      return;
    }
    const source = await voiceNoteAudioSource(note.id);
    player.replace(source);
    player.play();
    setPlayingId(note.id);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={styles.headerBar}>
        <TouchableOpacity
          onPress={() => (router.canGoBack() ? router.back() : router.replace("/today"))}
        >
          <Text style={{ color: colors.primary, fontWeight: "700" }}>← Quay lại</Text>
        </TouchableOpacity>
        <Text style={{ flex: 1, textAlign: "center", color: colors.text, fontWeight: "700" }}>
          Thư viện ghi âm
        </Text>
        <View style={{ width: 80 }} />
      </View>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
      >
      <View style={styles.card}>
        <View style={styles.filterRow}>
          <TouchableOpacity onPress={() => setFilter("today")}>
            <Text style={filter === "today" ? styles.chipActive : styles.chipInactive}>
              Hôm nay
            </Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setFilter("all")}>
            <Text style={filter === "all" ? styles.chipActive : styles.chipInactive}>
              Tất cả
            </Text>
          </TouchableOpacity>
        </View>
        <View style={styles.tagFilterRow}>
          <Field
            style={styles.tagField}
            placeholder="Lọc theo tag..."
            value={tagInput}
            onChangeText={setTagInput}
          />
          <TouchableOpacity onPress={handleFilterTag} style={styles.filterButton}>
            <Text style={{ color: colors.primary, fontWeight: "700" }}>Lọc</Text>
          </TouchableOpacity>
        </View>
      </View>

      {notes === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {notes?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>Chưa có ghi âm nào</Text>
      )}
      {notes && notes.length > 0 && (
        <View style={styles.card}>
          {notes.map((n) => (
            <VoiceNoteRow
              key={n.id}
              note={n}
              isCurrent={playingId === n.id}
              playing={playingId === n.id && status.playing}
              onToggle={() => toggle(n)}
            />
          ))}
        </View>
      )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  headerBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderColor: colors.divider,
    backgroundColor: colors.surface,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  filterRow: { flexDirection: "row", gap: spacing.lg },
  chipActive: { color: colors.primary, fontWeight: "700" },
  chipInactive: { color: colors.textSecondary, fontWeight: "400" },
  tagFilterRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  tagField: { flex: 1, marginBottom: 0 },
  filterButton: { paddingHorizontal: spacing.sm, paddingVertical: spacing.sm },
  row: {
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
    gap: spacing.xs,
  },
  playBtn: {
    backgroundColor: colors.primary,
    borderRadius: radius.sm,
    width: 36,
    height: 36,
    alignItems: "center",
    justifyContent: "center",
  },
  meta: { color: colors.textSecondary, fontSize: type.caption.fontSize },
});
