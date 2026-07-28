import React from "react";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import type { MainStackParamList } from "./types";
import { MainDrawer } from "./MainDrawer";
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
import { makeScreen } from "../errors/ScreenErrorBoundary";

// Khai báo ở mức module để đảm bảo stable reference — tránh tạo lại component
// mỗi lần MainNavigator re-render (gây mất state điều hướng).
const DrawerScreen = makeScreen(MainDrawer, "Drawer");
const TaskDetailScreen = makeScreen(TaskDetail, "TaskDetail");
const TeamScreen = makeScreen(Team, "Team");
const TeamDetailScreen = makeScreen(TeamDetail, "TeamDetail");
const NotesScreen = makeScreen(Notes, "Notes");
const InstructionsScreen = makeScreen(Instructions, "Instructions");
const SkillsScreen = makeScreen(Skills, "Skills");
const EmailsScreen = makeScreen(Emails, "Emails");
const PortalScreen = makeScreen(Portal, "Portal");
const ConversationsScreen = makeScreen(Conversations, "Conversations");
const ProjectsScreen = makeScreen(Projects, "Projects");
const NotificationsScreen = makeScreen(Notifications, "Notifications");
const ReportsScreen = makeScreen(Reports, "Reports");
const ReportSchedulesScreen = makeScreen(ReportSchedules, "ReportSchedules");
const AuditLogScreen = makeScreen(AuditLog, "AuditLog");
const VoiceNotesScreen = makeScreen(VoiceNotes, "VoiceNotes");

const Stack = createNativeStackNavigator<MainStackParamList>();

/** Stack chính: tab bar + mọi màn phụ (push từ Cài đặt/màn khác). Màn phụ tự render
 * <BackHeader/> nên headerShown=false. Hiệu ứng iOS slide + vuốt mép để back. */
export function MainNavigator() {
  return (
    <Stack.Navigator
      screenOptions={{ headerShown: false, animation: "slide_from_right", gestureEnabled: true }}
    >
      <Stack.Screen name="Drawer" component={DrawerScreen} />
      <Stack.Screen name="TaskDetail" component={TaskDetailScreen} />
      <Stack.Screen name="Team" component={TeamScreen} />
      <Stack.Screen name="TeamDetail" component={TeamDetailScreen} />
      <Stack.Screen name="Notes" component={NotesScreen} />
      <Stack.Screen name="Instructions" component={InstructionsScreen} />
      <Stack.Screen name="Skills" component={SkillsScreen} />
      <Stack.Screen name="Emails" component={EmailsScreen} />
      <Stack.Screen name="Portal" component={PortalScreen} />
      <Stack.Screen name="Conversations" component={ConversationsScreen} />
      <Stack.Screen name="Projects" component={ProjectsScreen} />
      <Stack.Screen name="Notifications" component={NotificationsScreen} />
      <Stack.Screen name="Reports" component={ReportsScreen} />
      <Stack.Screen name="ReportSchedules" component={ReportSchedulesScreen} />
      <Stack.Screen name="AuditLog" component={AuditLogScreen} />
      <Stack.Screen name="VoiceNotes" component={VoiceNotesScreen} />
    </Stack.Navigator>
  );
}
