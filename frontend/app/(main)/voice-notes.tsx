import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import {
  VoiceNote,
  deleteVoiceNote,
  listVoiceNotes,
  retranscribeVoiceNote,
  voiceNoteAudioSource,
} from "../../src/api/voice";
import { BackHeader } from "../../src/ui/BackHeader";
import { Field, ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";
import { formatDuration } from "../../src/util/format";

function todayIso(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function transcriptLine(n: VoiceNote): string {
  if (n.transcript) return n.transcript;
  switch (n.transcript_status) {
    case "queued":
    case "processing":
      return "⏳ Đang xử lý transcript…";
    case "failed":
      return "⚠️ Nhận dạng thất bại — bấm 'Nhận dạng lại'";
    default:
      return "🔇 Chưa bật nhận dạng giọng nói — transcript sẽ có khi bật STT";
  }
}

function VoiceNoteRow({
  note,
  isCurrent,
  playing,
  confirmingDelete,
  onToggle,
  onDelete,
  onRetranscribe,
}: {
  note: VoiceNote;
  isCurrent: boolean;
  playing: boolean;
  confirmingDelete: boolean;
  onToggle: () => void;
  onDelete: (id: string) => void;
  onRetranscribe: (id: string) => void;
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
            {note.title || new Date(note.created_at).toLocaleString("vi-VN")}
          </Text>
          <Text style={styles.meta}>
            {new Date(note.created_at).toLocaleString("vi-VN")}
            {note.duration_seconds != null ? ` · ${formatDuration(note.duration_seconds * 1000)}` : ""}
          </Text>
          {note.tags.length > 0 && (
            <Text style={styles.meta}>{note.tags.map((t) => `#${t}`).join(" · ")}</Text>
          )}
        </View>
      </View>
      <Text style={{ color: note.transcript ? colors.text : colors.textMuted }}>
        {transcriptLine(note)}
      </Text>
      {note.task_id && (
        <TouchableOpacity onPress={() => router.push(`/tasks/${note.task_id}`)}>
          <Text style={{ color: colors.primary, fontWeight: "700" }}>Xem task liên quan →</Text>
        </TouchableOpacity>
      )}
      <View style={{ flexDirection: "row", gap: spacing.md }}>
        {note.transcript_status === "failed" && (
          <TouchableOpacity onPress={() => onRetranscribe(note.id)}>
            <Text style={{ color: colors.primary, fontWeight: "700" }}>↻ Nhận dạng lại</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity onPress={() => onDelete(note.id)}>
          <Text style={{ color: colors.danger, fontWeight: "700" }}>
            {confirmingDelete ? "Chạm lần nữa để xóa!" : "🗑 Xóa"}
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

export default function VoiceNotesScreen() {
  const [filter, setFilter] = useState<"today" | "all">("all");
  const [tagInput, setTagInput] = useState("");
  const [tagFilter, setTagFilter] = useState<string | undefined>(undefined);
  const [notes, setNotes] = useState<VoiceNote[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const trackWidth = useRef(0);

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

  useEffect(() => {
    if (status.didJustFinish) {
      setPlayingId(null);
      player.seekTo(0);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.didJustFinish]);

  const handleFilterTag = () => {
    setTagFilter(tagInput.trim() || undefined);
  };

  const toggle = async (note: VoiceNote) => {
    setError(null);
    try {
      if (playingId === note.id) {
        if (status.playing) player.pause();
        else player.play();
        return;
      }
      const source = await voiceNoteAudioSource(note.id);
      player.replace(source);
      player.play();
      setPlayingId(note.id);
    } catch {
      setError("Không phát được ghi âm — thử lại.");
    }
  };

  const remove = async (id: string) => {
    if (confirmingDeleteId !== id) {
      setConfirmingDeleteId(id); // chạm 1: hỏi; chạm 2 mới xóa
      return;
    }
    setConfirmingDeleteId(null);
    try {
      await deleteVoiceNote(id);
      if (playingId === id) {
        player.pause(); // xoa note dang phat khong duoc de audio tiep tuc chay ngam
        setPlayingId(null);
      }
      load();
    } catch (e: any) {
      setError(String(e?.message ?? e));
    }
  };

  const retranscribe = async (id: string) => {
    try {
      await retranscribeVoiceNote(id);
      load();
    } catch (e: any) {
      setError(
        String(e?.message ?? "").includes("stt_not_configured")
          ? "Chưa cấu hình dịch vụ nhận dạng giọng nói."
          : "Không gửi được yêu cầu nhận dạng lại.",
      );
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <BackHeader title="Thư viện ghi âm" />
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
              confirmingDelete={confirmingDeleteId === n.id}
              onToggle={() => toggle(n)}
              onDelete={remove}
              onRetranscribe={retranscribe}
            />
          ))}
        </View>
      )}
      {playingId && status.duration > 0 && (
        <View style={styles.playerBar}>
          <Text style={styles.meta}>
            {formatDuration(status.currentTime * 1000)} / {formatDuration(status.duration * 1000)}
          </Text>
          <View
            style={styles.progressTrack}
            onStartShouldSetResponder={() => true}
            onResponderRelease={(e) => {
              const { locationX } = e.nativeEvent;
              if (trackWidth.current > 0)
                player.seekTo((locationX / trackWidth.current) * status.duration);
            }}
            onLayout={(e) => {
              trackWidth.current = e.nativeEvent.layout.width;
            }}
          >
            <View
              style={[styles.progressFill, { width: `${(status.currentTime / status.duration) * 100}%` }]}
            />
          </View>
        </View>
      )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
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
  playerBar: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    gap: spacing.xs,
  },
  progressTrack: {
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.divider,
    overflow: "hidden",
  },
  progressFill: { height: 8, backgroundColor: colors.primary },
});
