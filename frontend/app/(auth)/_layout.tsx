import { Redirect, Stack } from "expo-router";
import { useAuth } from "../../src/auth/AuthContext";

export default function AuthLayout() {
  const { user } = useAuth();
  if (user) return <Redirect href="/(main)/today" />;
  return <Stack screenOptions={{ headerTitleAlign: "center" }} />;
}
