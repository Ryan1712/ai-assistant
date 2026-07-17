import React, { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import {
  ChangeRoleResult,
  Device,
  TeamUser,
  changeRole,
  listUserDevices,
  listUsers,
  lockUser,
  offboardUser,
  unlockUser,
} from "../../../src/api/team";
import { ErrorText } from "../../../src/ui/form";
import { colors, radius, spacing, type } from "../../../src/ui/theme";

function roleLabel(role: TeamUser["role"]): string {
  return role === "ceo" ? "CEO" : role === "manager" ? "Manager" : "Nhân viên";
}

function PersonPicker({
  label,
  people,
  value,
  onChange,
}: {
  label: string;
  people: TeamUser[];
  value: string | null;
  onChange: (id: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = people.find((p) => p.id === value);
  return (
    <View style={{ marginTop: spacing.sm }}>
      <TouchableOpacity onPress={() => setOpen((o) => !o)}>
        <Text style={{ color: colors.primary }}>
          {label}: {selected ? selected.full_name : "Chưa chọn"}
        </Text>
      </TouchableOpacity>
      {open && (
        <View style={styles.pickerList}>
          {people.map((p) => (
            <TouchableOpacity
              key={p.id}
              onPress={() => {
                onChange(p.id);
                setOpen(false);
              }}
              style={styles.pickerRow}
            >
              <Text>{p.full_name}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

export default function TeamDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [users, setUsers] = useState<TeamUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lockBusy, setLockBusy] = useState(false);
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [devicesError, setDevicesError] = useState<string | null>(null);

  const [showOffboard, setShowOffboard] = useState(false);
  const [offboardSuccessor, setOffboardSuccessor] = useState<string | null>(null);
  const [offboardBusy, setOffboardBusy] = useState(false);
  const [offboardError, setOffboardError] = useState<string | null>(null);

  const [showRoleForm, setShowRoleForm] = useState(false);
  const [newRole, setNewRole] = useState<TeamUser["role"] | null>(null);
  const [newManager, setNewManager] = useState<string | null>(null);
  const [roleSuccessor, setRoleSuccessor] = useState<string | null>(null);
  const [roleBusy, setRoleBusy] = useState(false);
  const [roleError, setRoleError] = useState<string | null>(null);

  const load = () => {
    listUsers()
      .then(setUsers)
      .catch((e: any) => setError(String(e?.message ?? e)));
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!id) return;
    listUserDevices(id)
      .then(setDevices)
      .catch((e: any) => setDevicesError(String(e?.message ?? e)));
  }, [id]);

  const target = users?.find((u) => u.id === id) ?? null;
  const manager = target?.manager_id ? users?.find((u) => u.id === target.manager_id) : null;
  const successorCandidates =
    users?.filter((u) => u.id !== target?.id && u.status !== "locked") ?? [];
  const managerCandidates = users?.filter((u) => u.role === "manager") ?? [];

  const toggleLock = () => {
    if (!target) return;
    const locking = target.status === "active";
    Alert.alert(
      locking ? "Khóa tài khoản?" : "Mở khóa tài khoản?",
      locking
        ? `${target.full_name} sẽ bị đăng xuất khỏi mọi thiết bị.`
        : `${target.full_name} sẽ đăng nhập lại được.`,
      [
        { text: "Hủy", style: "cancel" },
        {
          text: locking ? "Khóa" : "Mở khóa",
          style: locking ? "destructive" : "default",
          onPress: async () => {
            setLockBusy(true);
            try {
              await (locking ? lockUser(target.id) : unlockUser(target.id));
              load();
            } catch (e: any) {
              Alert.alert("Không thực hiện được", String(e?.message ?? e));
            } finally {
              setLockBusy(false);
            }
          },
        },
      ],
    );
  };

  const submitOffboard = () => {
    if (!target) return;
    Alert.alert("Cho nghỉ việc?", `${target.full_name} sẽ bị khóa tài khoản ngay.`, [
      { text: "Hủy", style: "cancel" },
      {
        text: "Xác nhận",
        style: "destructive",
        onPress: async () => {
          setOffboardBusy(true);
          setOffboardError(null);
          try {
            await offboardUser(target.id, offboardSuccessor ?? undefined);
            setShowOffboard(false);
          } catch (e: any) {
            setOffboardError(String(e?.message ?? e));
          } finally {
            setOffboardBusy(false);
            load();
          }
        },
      },
    ]);
  };

  const submitRoleChange = async () => {
    if (!target) return;
    setRoleBusy(true);
    setRoleError(null);
    try {
      const result: ChangeRoleResult = await changeRole(target.id, {
        new_role: newRole ?? undefined,
        new_manager_id: newRole === "employee" ? newManager ?? undefined : undefined,
        successor_id: roleSuccessor ?? undefined,
      });
      void result;
      setShowRoleForm(false);
      load();
    } catch (e: any) {
      setRoleError(String(e?.message ?? e));
    } finally {
      setRoleBusy(false);
    }
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      {users === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {users !== null && !target && <ErrorText error="Không tìm thấy người này" />}
      {target && (
        <>
          <View style={styles.card}>
            <Text style={styles.title}>{target.full_name}</Text>
            <Text style={{ color: colors.textSecondary }}>{target.email}</Text>
            <Text style={{ marginTop: spacing.xs, color: colors.text }}>
              Vai trò: {roleLabel(target.role)}
            </Text>
            {manager && (
              <Text style={{ color: colors.text }}>Báo cáo cho: {manager.full_name}</Text>
            )}
            <Text style={{ color: target.status === "locked" ? colors.danger : colors.success }}>
              {target.status === "locked" ? "Đã khóa" : "Đang hoạt động"}
            </Text>
          </View>

          <View style={styles.card}>
            <Text style={styles.title}>Hành động</Text>

            <TouchableOpacity onPress={toggleLock} disabled={lockBusy}>
              {lockBusy ? (
                <ActivityIndicator color={colors.primary} />
              ) : (
                <Text style={{ color: colors.primary, fontWeight: "700" }}>
                  {target.status === "locked" ? "Mở khóa" : "Khóa tài khoản"}
                </Text>
              )}
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => setShowOffboard((s) => !s)}
              style={{ marginTop: spacing.md }}
            >
              <Text style={{ color: colors.danger, fontWeight: "700" }}>Cho nghỉ việc</Text>
            </TouchableOpacity>
            {showOffboard && (
              <View style={{ marginTop: spacing.sm }}>
                <PersonPicker
                  label="Người kế nhiệm (nếu cần)"
                  people={successorCandidates}
                  value={offboardSuccessor}
                  onChange={setOffboardSuccessor}
                />
                <ErrorText error={offboardError} />
                <TouchableOpacity
                  onPress={submitOffboard}
                  disabled={offboardBusy}
                  style={{ marginTop: spacing.sm }}
                >
                  {offboardBusy ? (
                    <ActivityIndicator color={colors.danger} />
                  ) : (
                    <Text style={{ color: colors.danger, fontWeight: "700" }}>
                      Xác nhận nghỉ việc
                    </Text>
                  )}
                </TouchableOpacity>
              </View>
            )}

            <TouchableOpacity
              onPress={() => {
                setShowRoleForm((s) => !s);
                setNewRole(target.role);
              }}
              style={{ marginTop: spacing.md }}
            >
              <Text style={{ color: colors.primary, fontWeight: "700" }}>Đổi vai trò</Text>
            </TouchableOpacity>
            {showRoleForm && (
              <View style={{ marginTop: spacing.sm }}>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  {(["ceo", "manager", "employee"] as const).map((r) => (
                    <TouchableOpacity
                      key={r}
                      onPress={() => setNewRole(r)}
                      style={[styles.chip, newRole === r && styles.chipActive]}
                    >
                      <Text style={{ color: newRole === r ? colors.onPrimary : colors.text }}>
                        {roleLabel(r)}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
                {newRole === "employee" && (
                  <PersonPicker
                    label="Quản lý"
                    people={managerCandidates}
                    value={newManager}
                    onChange={setNewManager}
                  />
                )}
                <PersonPicker
                  label="Người kế nhiệm (nếu cần)"
                  people={successorCandidates}
                  value={roleSuccessor}
                  onChange={setRoleSuccessor}
                />
                <ErrorText error={roleError} />
                <TouchableOpacity
                  onPress={submitRoleChange}
                  disabled={roleBusy}
                  style={{ marginTop: spacing.sm }}
                >
                  {roleBusy ? (
                    <ActivityIndicator color={colors.primary} />
                  ) : (
                    <Text style={{ color: colors.primary, fontWeight: "700" }}>Xác nhận</Text>
                  )}
                </TouchableOpacity>
              </View>
            )}
          </View>

          <View style={styles.card}>
            <Text style={styles.title}>Thiết bị đã đăng nhập</Text>
            {devices === null && !devicesError && <ActivityIndicator color={colors.primary} />}
            <ErrorText error={devicesError} />
            {devices?.length === 0 && (
              <Text style={{ color: colors.textMuted }}>Chưa có thiết bị nào đăng nhập</Text>
            )}
            {devices?.map((d) => (
              <View key={d.device_uuid} style={styles.deviceRow}>
                <Text style={type.body}>{d.device_name}</Text>
                <Text style={{ color: colors.textSecondary }}>
                  Đăng nhập gần nhất: {new Date(d.last_login_at).toLocaleString("vi-VN")}
                </Text>
              </View>
            ))}
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  title: { ...type.heading },
  chip: {
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
  },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  deviceRow: {
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
  pickerList: {
    marginTop: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
  },
  pickerRow: {
    padding: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
