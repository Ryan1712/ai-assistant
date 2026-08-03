import { createNavigationContainerRef } from "@react-navigation/native";

/**
 * Ref toàn cục cho NavigationContainer — cho phép điều hướng từ ngoài React context
 * (FAB toàn cục, push notification handler, crash reporter, v.v.).
 * Đăng ký ở App.tsx: <NavigationContainer ref={navigationRef}>.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const navigationRef = createNavigationContainerRef<any>();
