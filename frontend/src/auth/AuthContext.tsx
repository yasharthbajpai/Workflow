import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { AuthApi } from "../api/endpoints";
import { getToken, setToken } from "../api/client";
import type { Employee } from "../types";

interface AuthState {
  employee: Employee | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    AuthApi.me()
      .then(setEmployee)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const res = await AuthApi.login(email, password);
    setToken(res.access_token);
    setEmployee(res.employee);
  };

  const logout = () => {
    setToken(null);
    setEmployee(null);
    window.location.href = "/login";
  };

  return <AuthContext.Provider value={{ employee, loading, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
