import { Redirect } from "expo-router";
import { useAuth } from "../src/auth/AuthContext";

export default function Index() {
  const { user } = useAuth();
  return <Redirect href={user ? "/(main)/today" : "/(auth)/login"} />;
}
