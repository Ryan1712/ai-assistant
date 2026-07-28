/**
 * ScreenErrorBoundary.tsx — bộ chặn lỗi cấp màn hình.
 * Hiện UI dự phòng nhỏ gọn với nút "Thử lại" (ghost style) để tải lại màn hình.
 * Không che header/tab bar — chỉ bọc vùng nội dung của từng màn.
 */

import React from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { report } from "./crashReporter";
import { computeFingerprint } from "./fingerprint";
import { colors, fonts, spacing } from "../ui/theme";

interface Props {
  children: React.ReactNode;
  /** Tên màn hình — ghi vào crash payload để dễ phân tích */
  screenName?: string;
}

interface State {
  hasError: boolean;
  retryCount: number;
}

function generateEventId(): string {
  return `seb-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Bộ chặn lỗi cấp màn hình — bọc component trong Stack.Screen.
 * Dùng `makeScreen()` HOC để tạo component ổn định ở mức module.
 */
export class ScreenErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, retryCount: 0 };
  }

  static getDerivedStateFromError(_error: Error): Partial<State> {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    const fingerprint = computeFingerprint(
      "fe_boundary",
      error.message,
      error.stack,
    );

    report({
      source: "fe_boundary",
      severity: "error", // màn đơn lẻ — không fatal (header/tab vẫn hoạt động)
      message: error.message,
      stack: error.stack,
      component_stack: info.componentStack ?? undefined,
      screen: this.props.screenName,
      fingerprint,
      occurred_at: new Date().toISOString(),
      client_event_id: generateEventId(),
    });
  }

  private handleRetry = (): void => {
    this.setState((prev) => ({
      hasError: false,
      retryCount: prev.retryCount + 1,
    }));
  };

  render(): React.ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <View style={styles.container}>
        <Text style={styles.message}>Màn hình này gặp sự cố.</Text>
        <TouchableOpacity
          style={styles.button}
          onPress={this.handleRetry}
          accessibilityRole="button"
          accessibilityLabel="Thử lại tải màn hình"
        >
          <Text style={styles.buttonText}>Thử lại</Text>
        </TouchableOpacity>
      </View>
    );
  }
}

/**
 * HOC bọc component với ScreenErrorBoundary.
 * PHẢI khai báo ở mức module (không inline trong JSX) để tránh tạo lại
 * component mỗi lần navigator re-render — gây mất state điều hướng.
 *
 * @example
 * // Ở mức module, ngoài function navigator:
 * const WrappedChat = makeScreen(Chat, "Chat");
 * // Trong navigator:
 * <Stack.Screen name="Chat" component={WrappedChat} />
 */
export function makeScreen<P extends object>(
  Component: React.ComponentType<P>,
  screenName: string,
): React.ComponentType<P> {
  function WrappedScreen(props: P): React.ReactElement {
    return (
      <ScreenErrorBoundary screenName={screenName}>
        <Component {...props} />
      </ScreenErrorBoundary>
    );
  }
  WrappedScreen.displayName = `ScreenErrorBoundary(${screenName})`;
  return WrappedScreen;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.bg,
    padding: spacing.xl,
  },
  message: {
    fontFamily: fonts.regular,
    fontSize: 15,
    color: colors.textSecondary,
    textAlign: "center",
    marginBottom: spacing.lg,
  },
  button: {
    // Ghost button: viền primary, nền trong suốt
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    borderWidth: 1.5,
    borderColor: colors.primary,
    borderRadius: spacing.xxxl, // pill
  },
  buttonText: {
    fontFamily: fonts.semibold,
    fontSize: 15,
    color: colors.primary,
  },
});
