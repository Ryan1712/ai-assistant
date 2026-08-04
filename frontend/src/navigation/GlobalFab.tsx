/**
 * GlobalFab — bọc NewChatFab với logic ẩn/hiện theo navigation state.
 * Render một lần duy nhất trong MainNavigator, sibling của Stack.Navigator.
 * Ẩn khi route lá đang active là 'Chat'; hiện trên mọi route khác.
 */
import React from "react";
import { CommonActions, useNavigationState } from "@react-navigation/native";
import { NewChatFab } from "../ui/NewChatFab";
import { navigationRef } from "./navigationRef";
import { getActiveLeafRoute, type RouteState } from "./routeUtils";

export function GlobalFab() {
  // useNavigationState lấy Root Stack state (GlobalFab nằm trong MainNavigator
  // — screen của Root Stack — nên context gần nhất là Root Stack).
  // Root state chứa nested state của Main Stack và Drawer → đệ quy tìm leaf.
  const routeName = useNavigationState((s) => getActiveLeafRoute(s as RouteState));

  // Ẩn khi chưa hydrate (routeName undefined) hoặc đang ở Chat
  if (!routeName || routeName === "Chat") return null;

  return (
    <NewChatFab
      onPress={() => {
        // CommonActions.navigate bubbles xuống nested navigator, tìm 'Chat'
        // trong Drawer navigator rồi navigate tới đó.
        navigationRef.dispatch(CommonActions.navigate({ name: "Chat", params: {} }));
      }}
    />
  );
}
