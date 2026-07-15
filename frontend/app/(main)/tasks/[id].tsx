import React, { useEffect, useState } from "react";
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import * as DocumentPicker from "expo-document-picker";
import { TaskDetail, getTask } from "../../../src/api/tasks";
import {
  ATTACHMENT_MAX_SIZE,
  ATTACHMENT_MIME_TYPES,
  Attachment,
  listTaskAttachments,
  uploadTaskAttachment,
} from "../../../src/api/attachments";
import { ErrorText } from "../../../src/ui/form";
import { colors, radius, spacing, type } from "../../../src/ui/theme";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function AttachmentRow({ a }: { a: Attachment }) {
  return (
    <View style={styles.row}>
      <View style={{ flex: 1 }}>
        <Text numberOfLines={1}>{a.original_filename}</Text>
        <Text style={{ color: colors.textSecondary }}>
          {formatFileSize(a.file_size)} — {new Date(a.created_at).toLocaleDateString("vi-VN")}
        </Text>
      </View>
    </View>
  );
}

function AttachmentsSection({ taskId }: { taskId: string }) {
  const [attachments, setAttachments] = useState<Attachment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    listTaskAttachments(taskId)
      .then(setAttachments)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, [taskId]);

  const handlePick = async () => {
    const result = await DocumentPicker.getDocumentAsync({ type: ATTACHMENT_MIME_TYPES });
    if (result.canceled) return;
    const asset = result.assets[0];
    if (asset.size !== undefined && asset.size > ATTACHMENT_MAX_SIZE) {
      setError("File vượt quá 20MB.");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadTaskAttachment(taskId, {
        uri: asset.uri,
        name: asset.name,
        mimeType: asset.mimeType ?? "application/octet-stream",
      });
      setAttachments((prev) => (prev ? [uploaded, ...prev] : [uploaded]));
    } catch (e: any) {
      // ApiError.detail là chuỗi raw từ BE (vd "unsupported_file_format") — map sang
      // message tiếng Việt cho 2 lỗi 422 spec yêu cầu, còn lại dùng message chung.
      if (e?.status === 422 && e?.detail === "unsupported_file_format") {
        setError("Định dạng file không được hỗ trợ.");
      } else if (e?.status === 422 && e?.detail === "file_too_large") {
        setError("File vượt quá 20MB.");
      } else {
        setError(String(e?.message ?? e));
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <View style={styles.card}>
      <View style={styles.sectionHeader}>
        <Text style={styles.cardTitle}>Tài liệu đính kèm</Text>
        <TouchableOpacity
          onPress={handlePick}
          disabled={uploading}
          accessibilityLabel="Đính kèm tài liệu"
        >
          {uploading ? (
            <ActivityIndicator color={colors.primary} />
          ) : (
            <Text style={{ color: colors.primary, fontWeight: "700" }}>+ Đính kèm</Text>
          )}
        </TouchableOpacity>
      </View>
      {attachments === null && !error && <ActivityIndicator color={colors.primary} />}
      <ErrorText error={error} />
      {attachments?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>
          Chưa có tài liệu nào — bấm + Đính kèm để thêm
        </Text>
      )}
      {attachments?.map((a) => (
        <AttachmentRow key={a.id} a={a} />
      ))}
    </View>
  );
}

export default function TaskDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const t = await getTask(id);
        if (!cancelled) setTask(t);
      } catch (e: any) {
        if (!cancelled) setError(String(e?.message ?? e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      {!task && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {task && (
        <>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{task.title}</Text>
            <Text style={styles.meta}>
              {task.status} — {task.percent}%
            </Text>
            {task.description !== "" && <Text style={styles.body}>{task.description}</Text>}
            {task.deadline && (
              <Text style={styles.meta}>
                Deadline: {new Date(task.deadline).toLocaleDateString("vi-VN")}
              </Text>
            )}
            <Text style={styles.meta}>Ưu tiên: {task.priority}</Text>
          </View>
          <AttachmentsSection taskId={id} />
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  cardTitle: { ...type.heading },
  meta: { color: colors.textSecondary },
  body: { ...type.body },
  sectionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
