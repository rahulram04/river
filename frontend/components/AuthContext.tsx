"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { post, request } from "@/lib/api";
import type { User } from "@/lib/types";

type AuthState = { user: User | null; loading: boolean; refresh: () => Promise<void>; logout: () => Promise<void> };
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  async function refresh() {
    try { setUser(await request<User>("/api/auth/me")); }
    catch { setUser(null); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, []);
  async function logout() {
    await post("/api/auth/logout", {});
    setUser(null);
  }
  return <AuthContext.Provider value={{ user, loading, refresh, logout }}>{children}</AuthContext.Provider>;
}
export function useAuth() {
  const state = useContext(AuthContext);
  if (!state) throw new Error("AuthProvider is missing");
  return state;
}
