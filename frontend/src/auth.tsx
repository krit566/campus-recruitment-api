// Who is signed in. The token lives in sessionStorage; on load we ask the API who it belongs to (/auth/me), so a
// stale or tampered token never shows the wrong screens.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore, type Me } from "./api";

interface AuthState {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<Me>;
  register: (body: Record<string, unknown>) => Promise<Me>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(Boolean(tokenStore.get()));

  const logout = useCallback(() => {
    tokenStore.clear();
    setMe(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    if (tokenStore.get()) {
      api
        .me()
        .then(setMe)
        .catch(logout)
        .finally(() => setLoading(false));
    }
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const value = useMemo<AuthState>(
    () => ({
      me,
      loading,
      logout,
      login: async (email, password) => {
        const r = await api.login(email, password);
        tokenStore.set(r.access_token);
        setMe(r.me);
        return r.me;
      },
      register: async (body) => {
        const r = await api.register(body);
        tokenStore.set(r.access_token);
        setMe(r.me);
        return r.me;
      },
    }),
    [me, loading, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
