import React from "react";
import { Text } from "react-native";
import { Redirect, Tabs } from "expo-router";
import { useAuth } from "../../src/auth/AuthContext";
import { colors } from "../../src/ui/theme";

function Icon({ glyph }: { glyph: string }) {
  return <Text style={{ fontSize: 18 }}>{glyph}</Text>;
}

export default function MainLayout() {
  const { user } = useAuth();
  if (!user) return <Redirect href="/(auth)/login" />;
  return (
    <Tabs
      screenOptions={{
        headerTitleAlign: "center",
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textSecondary,
      }}
    >
      <Tabs.Screen
        name="today"
        options={{ title: "Hôm nay", tabBarIcon: () => <Icon glyph="📋" /> }}
      />
      <Tabs.Screen
        name="chat"
        options={{ title: "Trợ lý AI", tabBarIcon: () => <Icon glyph="💬" /> }}
      />
      <Tabs.Screen
        name="search"
        options={{ title: "Tìm kiếm", tabBarIcon: () => <Icon glyph="🔍" /> }}
      />
      <Tabs.Screen
        name="settings"
        options={{ title: "Cài đặt", tabBarIcon: () => <Icon glyph="⚙️" /> }}
      />
    </Tabs>
  );
}
