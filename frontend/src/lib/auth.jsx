import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | signed-in | signed-out

  const load = useCallback(async () => {
    if (!getToken()) {
      setStatus("signed-out");
      return;
    }
    try {
      setUser(await api.me());
      setStatus("signed-in");
    } catch {
      // api clears the token on 401; anything else means we cannot trust the
      // session either, so fall back to signed out.
      setToken("");
      setUser(null);
      setStatus("signed-out");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const signIn = useCallback(
    async (token) => {
      setToken(token);
      await load();
    },
    [load],
  );

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* Clear locally regardless: the user asked to leave. */
    }
    setToken("");
    setUser(null);
    setStatus("signed-out");
  }, []);

  const value = useMemo(() => ({ user, status, signIn, signOut, reload: load }), [user, status, signIn, signOut, load]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
