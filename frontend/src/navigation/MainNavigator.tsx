import React from "react";
import { StyleSheet, View } from "react-native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import type { MainStackParamList } from "./types";
import { MainDrawer } from "./MainDrawer";
import { GlobalFab } from "./GlobalFab";
import TaskDetail from "../../app/main/tasks/detail";
import Team from "../../app/main/team";
import TeamDetail from "../../app/main/team/detail";
import Notes from "../../app/main/notes";
import Instructions from "../../app/main/instructions";
import Skills from "../../app/main/skills";
import Emails from "../../app/main/emails";
import Portal from "../../app/main/portal";
import Conversations from "../../app/main/conversations";
import Projects from "../../app/main/projects";
import Notifications from "../../app/main/notifications";
import Reports from "../../app/main/reports";
import ReportSchedules from "../../app/main/report-schedules";
import AuditLog from "../../app/main/audit-log";
import VoiceNotes from "../../app/main/voice-notes";

const Stack = createNativeStackNavigator<MainStackParamList>();

/** Stack chính: tab bar + mọi màn phụ (push từ Cài đặt/màn khác). Màn phụ tự render
 * <BackHeader/> nên headerShown=false. Hiệu ứng iOS slide + vuốt mép để back.
 * GlobalFab render một lần ở đây, sibling của Stack.Navigator — ẩn/hiện tự động. */
export function MainNavigator() {
  return (
    <View style={styles.root}>
      <Stack.Navigator
        screenOptions={{ headerShown: false, animation: "slide_from_right", gestureEnabled: true }}
      >
        <Stack.Screen name="Drawer" component={MainDrawer} />
        <Stack.Screen name="TaskDetail" component={TaskDetail} />
        <Stack.Screen name="Team" component={Team} />
        <Stack.Screen name="TeamDetail" component={TeamDetail} />
        <Stack.Screen name="Notes" component={Notes} />
        <Stack.Screen name="Instructions" component={Instructions} />
        <Stack.Screen name="Skills" component={Skills} />
        <Stack.Screen name="Emails" component={Emails} />
        <Stack.Screen name="Portal" component={Portal} />
        <Stack.Screen name="Conversations" component={Conversations} />
        <Stack.Screen name="Projects" component={Projects} />
        <Stack.Screen name="Notifications" component={Notifications} />
        <Stack.Screen name="Reports" component={Reports} />
        <Stack.Screen name="ReportSchedules" component={ReportSchedules} />
        <Stack.Screen name="AuditLog" component={AuditLog} />
        <Stack.Screen name="VoiceNotes" component={VoiceNotes} />
      </Stack.Navigator>
      {/* FAB toàn cục — nổi trên Stack, ẩn khi route lá là 'Chat' */}
      <GlobalFab />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});
