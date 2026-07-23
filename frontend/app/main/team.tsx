import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { TeamUser, listUsers } from "../../src/api/team";
import { BackHeader } from "../../src/ui/BackHeader";
import { ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

function roleLabel(role: TeamUser["role"]): string {
  return role === "ceo" ? "CEO" : role === "manager" ? "Manager" : "Nhân viên";
}

function TeamRow({ u }: { u: TeamUser }) {
  const navigation = useNavigation<any>();
  return (
    <TouchableOpacity style={styles.row} onPress={() => navigation.navigate("TeamDetail", { id: u.id })}>
      <View style={{ flex: 1 }}>
        <Text style={type.body}>{u.full_name}</Text>
        <Text style={{ color: colors.textSecondary }}>{roleLabel(u.role)}</Text>
      </View>
      {u.status === "locked" && (
        <Text style={{ color: colors.danger, fontWeight: "700" }}>Đã khóa</Text>
      )}
    </TouchableOpacity>
  );
}

export default function Team() {
  const [users, setUsers] = useState<TeamUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listUsers()
      .then(setUsers)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, []);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <BackHeader title="Team" />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
      >
      {users === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {users?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>Chưa có ai trong công ty</Text>
      )}
      {users && users.length > 0 && (
        <View style={styles.card}>
          {users.map((u) => (
            <TeamRow key={u.id} u={u} />
          ))}
        </View>
      )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
