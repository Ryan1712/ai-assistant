/**
 * ErrorBoundary.tsx — bộ chặn lỗi cấp gốc của cây component.
 * Khi component con crash khi render, hiện UI dự phòng thay vì crash app.
 * Gọi crashReporter.report() để ghi nhận lỗi.
 *
 * Dùng class component vì React Error Boundary yêu cầu lifecycle getDerivedStateFromError
 * và componentDidCatch — không thể dùng function component.
 */

import React from "react";
import {
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { report } from "./crashReporter";
import { computeFingerprint } from "./fingerprint";
import { colors, fonts, spacing } from "../ui/theme";

interface Props {
  children: React.ReactNode;
  /** UI dự phòng tuỳ chỉnh — nếu không truyền, dùng fallback mặc định */
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
}

function generateEventId(): string {
  return `eb-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Bộ chặn lỗi cấp gốc — bọc ngoài cùng của cây component (bên trong GestureHandlerRootView).
 * Bắt mọi lỗi render của cây con, hiện UI dự phòng và ghi nhận vào crash reporter.
 */
export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(_error: Error): State {
    // Cập nhật state để hiện UI dự phòng trong lần render tiếp theo
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    const fingerprint = computeFingerprint(
      "fe_boundary",
      error.message,
      error.stack,
    );

    // Ghi nhận lỗi vào hàng đợi — không await (componentDidCatch không hỗ trợ async)
    report({
      source: "fe_boundary",
      severity: "fatal",
      message: error.message,
      stack: error.stack,
      component_stack: info.componentStack ?? undefined,
      fingerprint,
      occurred_at: new Date().toISOString(),
      client_event_id: generateEventId(),
    });
  }

  private handleRestart = (): void => {
    this.setState({ hasError: false });
  };

  render(): React.ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    // Dùng custom fallback nếu được cung cấp
    if (this.props.fallback !== undefined) {
      return this.props.fallback;
    }

    return (
      <View style={styles.container} testID="error-fallback">
        <Text style={styles.icon}>✦</Text>
        <Text style={styles.title}>Ối, có lỗi xảy ra!</Text>
        <Text style={styles.message}>
          Ứng dụng gặp sự cố không mong muốn.{"\n"}Vui lòng thử lại.
        </Text>
        <TouchableOpacity
          style={styles.button}
          onPress={this.handleRestart}
          accessibilityRole="button"
          accessibilityLabel="Khởi động lại ứng dụng"
        >
          <Text style={styles.buttonText}>Khởi động lại</Text>
        </TouchableOpacity>
      </View>
    );
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.bg,
    paddingHorizontal: spacing.xl,
    // Padding an toàn thủ công (ErrorBoundary nằm ngoài SafeAreaProvider)
    paddingTop: Platform.select({ ios: 44, android: 24, default: 0 }),
  },
  icon: {
    fontSize: 48,
    marginBottom: spacing.lg,
    color: colors.dangerText,
  },
  title: {
    fontFamily: fonts.bold,
    fontSize: 20,
    color: colors.text,
    marginBottom: spacing.sm,
    textAlign: "center",
  },
  message: {
    fontFamily: fonts.regular,
    fontSize: 15,
    color: colors.textSecondary,
    textAlign: "center",
    lineHeight: 22,
    marginBottom: spacing.xl,
  },
  button: {
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    backgroundColor: colors.primary,
    borderRadius: spacing.xxxl, // pill
  },
  buttonText: {
    fontFamily: fonts.bold,
    fontSize: 15,
    color: colors.onPrimary,
  },
});
