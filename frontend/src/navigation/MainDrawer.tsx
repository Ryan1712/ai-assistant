import React from "react";
import { createDrawerNavigator } from "@react-navigation/drawer";
import { colors, fonts } from "../ui/theme";
import type { DrawerParamList } from "./types";
import { DrawerContent } from "./DrawerContent";
import Chat from "../../app/main/chat";
import Today from "../../app/main/today";
import Tasks from "../../app/main/tasks";
import Settings from "../../app/main/settings";

const Drawer = createDrawerNavigator<DrawerParamList>();

/** Thay cho TabNavigator: mặc định vào Chat, nút menu mở drawer kiểu Claude
 * (menu items trên + recents dưới — xem DrawerContent). */
export function MainDrawer() {
  return (
    <Drawer.Navigator
      initialRouteName="Chat"
      drawerContent={(props) => <DrawerContent {...props} />}
      screenOptions={{
        drawerType: "front",
        headerStyle: { backgroundColor: colors.surface },
        headerShadowVisible: false,
        headerTitleAlign: "center",
        headerTintColor: colors.text,
        headerTitleStyle: { fontFamily: fonts.bold, fontSize: 17, color: colors.text },
      }}
    >
      <Drawer.Screen name="Chat" component={Chat} options={{ headerShown: false }} />
      <Drawer.Screen name="Today" component={Today} options={{ title: "Dashboard" }} />
      <Drawer.Screen name="Tasks" component={Tasks} options={{ title: "Công việc" }} />
      <Drawer.Screen name="Settings" component={Settings} options={{ title: "Cài đặt" }} />
    </Drawer.Navigator>
  );
}
