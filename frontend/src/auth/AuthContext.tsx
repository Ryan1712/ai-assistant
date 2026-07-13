import React, { createContext, useContext, useEffect, useState } from "react";
import { Platform } from "react-native";
import { apiFetch } from "../api/client";
import { registerPushTokenBestEffort } from "../notifications/push";
import { clearTokens, getDeviceUuid, getTokens, setTokens } from "./tokenStore";

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: "ceo" | "manager" | "employee";
  is_root: boolean;
};

type AuthOut = { access_token: string; refresh_token: string; user: User };

type AuthState = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signupWorkspace: (v: {
    workspace_name: string;
    email: string;
    password: string;
    full_name: string;
  }) => Promise<void>;
  signupCode: (v: {
    invite_code: string;
    email: string;
    password: string;
    full_name: string;
  }) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

async function deviceFields() {
  return {
    device_uuid: await getDeviceUuid(),
    device_name: `${Platform.OS} app`,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Khôi phục phiên: có token thì thử gọi 1 endpoint nhẹ để xác thực
    (async () => {
      try {
        const tokens = await getTokens();
        if (tokens) {
          const me = await apiFetch<User>("/api/v1/users/me");
          setUser(me);
        }
      } catch {
        await clearTokens();
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    // Sau đăng nhập / khôi phục phiên: đăng ký push token (guarded, không await)
    if (user) registerPushTokenBestEffort();
  }, [user?.id]);

  const finishAuth = async (out: AuthOut) => {
    await setTokens({ access_token: out.access_token, refresh_token: out.refresh_token });
    setUser(out.user);
  };

  const value: AuthState = {
    user,
    loading,
    login: async (email, password) => {
      const out = await apiFetch<AuthOut>("/api/v1/auth/login", {
        method: "POST",
        auth: false,
        body: { email, password, ...(await deviceFields()) },
      });
      await finishAuth(out);
    },
    signupWorkspace: async (v) => {
      const out = await apiFetch<AuthOut>("/api/v1/auth/signup-workspace", {
        method: "POST",
        auth: false,
        body: { ...v, ...(await deviceFields()) },
      });
      await finishAuth(out);
    },
    signupCode: async (v) => {
      const out = await apiFetch<AuthOut>("/api/v1/auth/signup-code", {
        method: "POST",
        auth: false,
        body: { ...v, ...(await deviceFields()) },
      });
      await finishAuth(out);
    },
    signOut: async () => {
      const tokens = await getTokens();
      if (tokens?.refresh_token) {
        try {
          await apiFetch("/api/v1/auth/logout", {
            method: "POST",
            body: { refresh_token: tokens.refresh_token },
          });
        } catch {}
      }
      await clearTokens();
      setUser(null);
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
