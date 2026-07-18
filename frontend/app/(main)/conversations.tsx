import React, { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import {
  Conversation,
  createConversation,
  listConversations,
  renameConversation,
} from "../../src/api/chat";
import { BackHeader } from "../../src/ui/BackHeader";
import { ErrorText, Field } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

function ConversationRow({
  c,
  onRenamed,
}: {
  c: Conversation;
  onRenamed: (id: string, title: string) => void;
}) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(c.title ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const title = draft.trim();
    if (!title) return;
    setBusy(true);
    setError(null);
    try {
      await renameConversation(c.id, title);
      onRenamed(c.id, title);
      setEditing(false);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  if (editing) {
    return (
      <View style={styles.row}>
        <Field value={draft} onChangeText={setDraft} autoFocus style={{ marginBottom: spacing.xs }} />
        <ErrorText error={error} />
        <View style={{ flexDirection: "row", gap: spacing.lg }}>
          <TouchableOpacity onPress={() => setEditing(false)} disabled={busy}>
            <Text style={{ color: colors.textSecondary, fontWeight: "700" }}>Hủy</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={save} disabled={busy}>
            {busy ? (
              <ActivityIndicator color={colors.primary} />
            ) : (
              <Text style={{ color: colors.primary, fontWeight: "700" }}>Lưu</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.row}>
      <TouchableOpacity style={{ flex: 1 }} onPress={() => router.push(`/chat?id=${c.id}`)}>
        <Text style={type.body} numberOfLines={1}>
          {c.title || "Cuộc trò chuyện chưa đặt tên"}
        </Text>
        <Text style={{ color: colors.textSecondary }}>
          {new Date(c.created_at).toLocaleString("vi-VN")}
          {c.queue_held ? " — ⏸ có việc dang dở" : ""}
        </Text>
      </TouchableOpacity>
      <TouchableOpacity
        onPress={() => {
          setDraft(c.title ?? "");
          setEditing(true);
        }}
      >
        <Text style={{ color: colors.primary, fontWeight: "700" }}>Sửa</Text>
      </TouchableOpacity>
    </View>
  );
}

export default function Conversations() {
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    listConversations()
      .then(setConversations)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, []);

  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    try {
      const conv = await createConversation();
      router.push(`/chat?id=${conv.id}`);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setCreating(false);
    }
  };

  const filtered =
    conversations?.filter((c) =>
      (c.title ?? "").toLowerCase().includes(query.trim().toLowerCase()),
    ) ?? null;

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <BackHeader title="Lịch sử trò chuyện" />
      <View style={{ flex: 1, padding: spacing.md, gap: spacing.md }}>
      <TouchableOpacity style={styles.newBtn} onPress={handleCreate} disabled={creating}>
        {creating ? (
          <ActivityIndicator color={colors.onPrimary} />
        ) : (
          <Text style={{ color: colors.onPrimary, fontWeight: "700" }}>
            + Cuộc trò chuyện mới
          </Text>
        )}
      </TouchableOpacity>
      <Field
        placeholder="Tìm cuộc trò chuyện theo tên..."
        value={query}
        onChangeText={setQuery}
        style={{ marginBottom: 0 }}
      />
      {conversations === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {filtered?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>Không có cuộc trò chuyện nào</Text>
      )}
      {filtered && filtered.length > 0 && (
        <View style={styles.card}>
          {filtered.map((c) => (
            <ConversationRow
              key={c.id}
              c={c}
              onRenamed={(id, title) =>
                setConversations((prev) =>
                  prev ? prev.map((x) => (x.id === id ? { ...x, title } : x)) : prev,
                )
              }
            />
          ))}
        </View>
      )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  newBtn: {
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    alignItems: "center",
  },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  row: {
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
  },
});
