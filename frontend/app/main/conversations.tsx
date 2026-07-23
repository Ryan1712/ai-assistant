import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Modal,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import ReanimatedSwipeable from "react-native-gesture-handler/ReanimatedSwipeable";
import {
  Conversation,
  createConversation,
  deleteConversation,
  listConversations,
  renameConversation,
} from "../../src/api/chat";
import { BackHeader } from "../../src/ui/BackHeader";
import { ErrorText, Field } from "../../src/ui/form";
import { colors, fonts, radius, shadow, spacing, type } from "../../src/ui/theme";

function ConversationRow({
  c,
  onEdit,
  onDelete,
}: {
  c: Conversation;
  onEdit: (c: Conversation) => void;
  onDelete: (c: Conversation) => void;
}) {
  const navigation = useNavigation<any>();
  const swipeRef = useRef<any>(null);

  const renderRightActions = () => (
    <View style={styles.actions}>
      <TouchableOpacity
        style={[styles.actionBtn, styles.editBtn]}
        onPress={() => {
          swipeRef.current?.close();
          onEdit(c);
        }}
        accessibilityLabel="Sửa tên"
      >
        <Ionicons name="pencil" size={18} color="#fff" />
        <Text style={styles.actionText}>Sửa</Text>
      </TouchableOpacity>
      <TouchableOpacity
        style={[styles.actionBtn, styles.deleteBtn]}
        onPress={() => {
          swipeRef.current?.close();
          onDelete(c);
        }}
        accessibilityLabel="Xoá cuộc trò chuyện"
      >
        <Ionicons name="trash" size={18} color="#fff" />
        <Text style={styles.actionText}>Xoá</Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <ReanimatedSwipeable
      ref={swipeRef}
      renderRightActions={renderRightActions}
      rightThreshold={40}
      overshootRight={false}
      friction={2}
    >
      <TouchableOpacity
        style={styles.row}
        activeOpacity={0.7}
        onPress={() => navigation.navigate("Drawer", { screen: "Chat", params: { id: c.id } })}
      >
        <View style={{ flex: 1 }}>
          <Text style={type.body} numberOfLines={1}>
            {c.title || "Cuộc trò chuyện chưa đặt tên"}
          </Text>
          <Text style={styles.meta}>
            {new Date(c.created_at).toLocaleString("vi-VN")}
            {c.queue_held ? " — ⏸ có việc dang dở" : ""}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
      </TouchableOpacity>
    </ReanimatedSwipeable>
  );
}

export default function Conversations() {
  const navigation = useNavigation<any>();
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);

  // Modal sửa tên
  const [editing, setEditing] = useState<Conversation | null>(null);
  const [draft, setDraft] = useState("");
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

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
      navigation.navigate("Drawer", { screen: "Chat", params: { id: conv.id } });
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setCreating(false);
    }
  };

  const openEdit = (c: Conversation) => {
    setDraft(c.title ?? "");
    setEditError(null);
    setEditing(c);
  };

  const saveEdit = async () => {
    if (!editing) return;
    const title = draft.trim();
    if (!title) return;
    setEditBusy(true);
    setEditError(null);
    try {
      await renameConversation(editing.id, title);
      setConversations((prev) =>
        prev ? prev.map((x) => (x.id === editing.id ? { ...x, title } : x)) : prev,
      );
      setEditing(null);
    } catch (e: any) {
      setEditError(String(e?.message ?? e));
    } finally {
      setEditBusy(false);
    }
  };

  const handleDelete = (c: Conversation) => {
    Alert.alert(
      "Xoá cuộc trò chuyện",
      `Bạn có muốn xoá "${c.title || "cuộc trò chuyện này"}" không? Toàn bộ tin nhắn sẽ bị xoá.`,
      [
        { text: "Hủy", style: "cancel" },
        {
          text: "Xoá",
          style: "destructive",
          onPress: async () => {
            try {
              await deleteConversation(c.id);
              setConversations((prev) => (prev ? prev.filter((x) => x.id !== c.id) : prev));
            } catch (e: any) {
              setError(String(e?.message ?? e));
            }
          },
        },
      ],
    );
  };

  const filtered =
    conversations?.filter((c) =>
      (c.title ?? "").toLowerCase().includes(query.trim().toLowerCase()),
    ) ?? null;

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <BackHeader title="Lịch sử trò chuyện" />
      <View style={styles.body}>
        <TouchableOpacity style={styles.newBtn} onPress={handleCreate} disabled={creating}>
          {creating ? (
            <ActivityIndicator color={colors.onPrimary} />
          ) : (
            <Text style={styles.newBtnText}>+ Cuộc trò chuyện mới</Text>
          )}
        </TouchableOpacity>

        <Field
          placeholder="Tìm cuộc trò chuyện theo tên…"
          value={query}
          onChangeText={setQuery}
          returnKeyType="search"
          style={{ marginBottom: 0 }}
        />

        {conversations === null && !error && (
          <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
        )}
        <ErrorText error={error} />
        {filtered?.length === 0 && (
          <Text style={styles.empty}>Không có cuộc trò chuyện nào</Text>
        )}
        {filtered && filtered.length > 0 && (
          <View style={styles.card}>
            {filtered.map((c, i) => (
              <View key={c.id} style={i > 0 ? styles.divider : undefined}>
                <ConversationRow c={c} onEdit={openEdit} onDelete={handleDelete} />
              </View>
            ))}
          </View>
        )}
      </View>

      {/* Modal sửa tên cuộc trò chuyện */}
      <Modal visible={!!editing} transparent animationType="fade" onRequestClose={() => setEditing(null)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Sửa tên cuộc trò chuyện</Text>
            <Field
              value={draft}
              onChangeText={setDraft}
              autoFocus
              placeholder="Tên cuộc trò chuyện"
              style={{ marginBottom: spacing.sm }}
            />
            <ErrorText error={editError} />
            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.modalCancel}
                onPress={() => setEditing(null)}
                disabled={editBusy}
              >
                <Text style={styles.modalCancelText}>Hủy</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalSave} onPress={saveEdit} disabled={editBusy}>
                {editBusy ? (
                  <ActivityIndicator color={colors.onPrimary} />
                ) : (
                  <Text style={styles.modalSaveText}>Lưu</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  body: { flex: 1, padding: spacing.lg, gap: spacing.lg },
  newBtn: {
    backgroundColor: colors.primary,
    borderRadius: radius.pill,
    paddingVertical: spacing.md,
    alignItems: "center",
  },
  newBtnText: { color: colors.onPrimary, fontFamily: fonts.bold, fontSize: 16 },

  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden", // để action swipe bo theo góc card
  },
  divider: { borderTopWidth: 1, borderColor: colors.divider },
  row: {
    backgroundColor: colors.surface,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  meta: { color: colors.textSecondary, fontSize: 13, marginTop: 2 },
  empty: { color: colors.textMuted, textAlign: "center", marginTop: spacing.xl },

  // Nút lộ ra khi swipe
  actions: { flexDirection: "row" },
  actionBtn: { width: 76, alignItems: "center", justifyContent: "center", gap: 3 },
  editBtn: { backgroundColor: colors.info },
  deleteBtn: { backgroundColor: colors.danger },
  actionText: { color: "#fff", fontFamily: fonts.semibold, fontSize: 13 },

  // Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "center",
    padding: spacing.xl,
  },
  modalCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.lg,
    ...shadow.card,
  },
  modalTitle: { fontFamily: fonts.bold, fontSize: 18, color: colors.text, marginBottom: spacing.md },
  modalActions: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.xs },
  modalCancel: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  modalCancelText: { color: colors.textSecondary, fontFamily: fonts.bold, fontSize: 15 },
  modalSave: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  modalSaveText: { color: colors.onPrimary, fontFamily: fonts.bold, fontSize: 15 },
});
