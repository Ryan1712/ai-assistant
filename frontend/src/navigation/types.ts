/** Kiểu điều hướng react-navigation. Giữ nhẹ — screen dùng useNavigation<any>()
 * cho gọn, nhưng param list ở đây giúp navigate() có gợi ý ở nơi cần. */

export type DrawerParamList = {
  Chat: { id?: string } | undefined;
  Today: undefined;
  Tasks: undefined;
  Settings: undefined;
};

export type MainStackParamList = {
  Drawer: { screen?: keyof DrawerParamList; params?: DrawerParamList[keyof DrawerParamList] } | undefined;
  TaskDetail: { id: string };
  Team: undefined;
  TeamDetail: { id: string };
  Notes: undefined;
  Instructions: undefined;
  Skills: undefined;
  Emails: undefined;
  Portal: undefined;
  Conversations: undefined;
  Projects: undefined;
  Notifications: undefined;
  Reports: undefined;
  ReportSchedules: undefined;
  AuditLog: undefined;
  VoiceNotes: undefined;
};

export type AuthStackParamList = {
  Login: undefined;
  ForgotPassword: undefined;
  SignupCode: undefined;
  SignupWorkspace: undefined;
};
