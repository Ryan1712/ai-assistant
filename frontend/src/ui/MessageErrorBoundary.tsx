import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { colors, radius, spacing } from "./theme";

type Props = { children: React.ReactNode };
type State = { hasError: boolean };

/**
 * Bọc quanh MỘT dòng tin nhắn trong danh sách chat. App chưa có error boundary
 * nào — bất kỳ exception nào lúc render (vd thư viện Markdown parse phải
 * markdown lệch cú pháp) trước đây làm SẬP TOÀN BỘ app (bug thật 2026-07-27:
 * "**text**" chưa đóng dấu giữa lúc stream). Bọc per-item để 1 dòng lỗi chỉ
 * hiện fallback tại chỗ, các dòng khác trong hội thoại vẫn đọc được bình thường.
 */
export class MessageErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    console.error("MessageErrorBoundary bắt được lỗi render tin nhắn:", error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <View style={styles.wrap}>
          <Text style={styles.text}>Không hiển thị được tin nhắn này.</Text>
        </View>
      );
    }
    return this.props.children;
  }
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: colors.dangerBg,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  text: { color: colors.danger, fontSize: 13 },
});
