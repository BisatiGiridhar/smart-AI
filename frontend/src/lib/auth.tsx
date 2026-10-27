import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, session } from "./api";
import type { Me, Role } from "./types";

type AuthState = { me: Me | null; loading: boolean; login: (email: string, password: string) => Promise<void>; logout: () => Promise<void>; switchWorkspace: (id: string) => Promise<void>; can: (...roles: Role[]) => boolean };
const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!session.token) { setMe(null); setLoading(false); return; }
    try { setMe(await api<Me>("/api/auth/me")); } catch { setMe(null); } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    refresh();
    const onUnauth = () => setMe(null);
    window.addEventListener("saiha:unauthorized", onUnauth);
    return () => window.removeEventListener("saiha:unauthorized", onUnauth);
  }, [refresh]);

  const login = async (email: string, password: string) => {
    const res = await api<{ access_token: string }>("/api/auth/login", { method: "POST", json: { email, password } });
    session.token = res.access_token;
    await refresh();
  };
  const logout = async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } catch { /* token may already be invalid */ }
    session.token = null; session.workspace = null; setMe(null);
  };
  const switchWorkspace = async (id: string) => { session.workspace = id; await refresh(); };
  const can = (...roles: Role[]) => !!me && roles.includes(me.role);
  return <Ctx.Provider value={{ me, loading, login, logout, switchWorkspace, can }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
