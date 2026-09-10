import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { AuthApi } from "../api/endpoints";
import type { Employee } from "../types";

const DEMO_PASSWORD = "Nortex@123"; // shared demo password for every seeded account

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [demoUsers, setDemoUsers] = useState<Employee[]>([]);

  useEffect(() => {
    AuthApi.demoUsers()
      .then(setDemoUsers)
      .catch(() => setDemoUsers([]));
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/");
    } catch {
      setError("Invalid email or password");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="grid w-full max-w-4xl grid-cols-1 gap-8 md:grid-cols-2">
        <div className="rounded-xl border bg-white p-8 shadow-sm">
          <h1 className="text-xl font-bold text-slate-800">Nortex Travel &amp; Expense</h1>
          <p className="mt-1 text-sm text-slate-500">Sign in with any seeded employee account.</p>
          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-600">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="chaitanya.reddy@nortexindustries.com"
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600">Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
          <p className="mt-4 text-xs text-slate-400">
            Every demo account shares the password <span className="font-mono">{DEMO_PASSWORD}</span>.
          </p>
        </div>

        <div className="rounded-xl border bg-white p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-700">Demo accounts</h2>
          <ul className="mt-3 max-h-96 space-y-1 overflow-auto text-sm">
            {demoUsers.map((u) => (
              <li key={u.emp_code}>
                <button
                  className="w-full rounded-md px-2 py-1.5 text-left hover:bg-slate-50"
                  onClick={() => {
                    setEmail(u.email);
                    setPassword(DEMO_PASSWORD);
                  }}
                >
                  <span className="font-medium text-slate-800">{u.name}</span>
                  <span className="ml-2 text-xs text-slate-400">
                    {u.designation} · {u.role_code}
                  </span>
                  <div className="text-xs text-slate-400">{u.email}</div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
