/**
 * GlobalFab — bọc NewChatFab với logic ẩn/hiện theo navigation state.
 * Render một lần duy nhất trong MainNavigator, sibling của Stack.Navigator.
 * Ẩn khi route lá đang active là 'Chat'; hiện trên mọi route khác.
 *
 * Hành động "Cuộc trò chuyện mới":
 *  1. Gọi createConversation() để lấy id mới từ server.
 *  2. Điều hướng đến "Chat" với id đó — params KHÁC → React Navigation reload → màn trắng.
 * Lý do cần bước 1: nếu chỉ navigate("Chat", {}) mà đang ở Chat(id:...) thì params
 * không đổi đủ → short-circuit → màn không trắng được.
 */
import React from "react";
import { CommonActions, useNavigationState } from "@react-navigation/native";
import { NewChatFab } from "../ui/NewChatFab";
import { navigationRef } from "./navigationRef";
import { getActiveLeafRoute, type RouteState } from "./routeUtils";
import { createConversation } from "../api/chat";

export function GlobalFab() {
  // useNavigationState lấy Root Stack state (GlobalFab nằm trong MainNavigator
  // — screen của Root Stack — nên context gần nhất là Root Stack).
  // Root state chứa nested state của Main Stack và Drawer → đệ quy tìm leaf.
  const routeName = useNavigationState((s) => getActiveLeafRoute(s as RouteState));

  // Ẩn khi chưa hydrate (routeName undefined) hoặc đang ở Chat
  if (!routeName || routeName === "Chat") return null;

  return (
    <NewChatFab
      onPress={async () => {
        try {
          const conv = await createConversation();
          navigationRef.dispatch(
            CommonActions.navigate({ name: "Chat", params: { id: conv.id } }),
          );
        } catch {
          // Nếu mạng lỗi: vẫn điều hướng về Chat active (id: undefined) thay vì crash
          navigationRef.dispatch(
            CommonActions.navigate({ name: "Chat", params: { id: undefined } }),
          );
        }
      }}
    />
  );
}
