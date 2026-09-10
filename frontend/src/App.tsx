import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { LoginPage } from "./pages/Login";
import { DashboardPage } from "./pages/Dashboard";
import { SubmitPage } from "./pages/Submit";
import { ApprovalsPage } from "./pages/Approvals";
import { FinancePage } from "./pages/Finance";
import { ClaimDetailPage } from "./pages/ClaimDetail";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { employee, loading } = useAuth();
  if (loading) return <div className="p-8 text-sm text-slate-400">Loading…</div>;
  if (!employee) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <RequireAuth>
                  <Layout />
                </RequireAuth>
              }
            >
              <Route path="/" element={<DashboardPage />} />
              <Route path="/submit" element={<SubmitPage />} />
              <Route path="/approvals" element={<ApprovalsPage />} />
              <Route path="/finance" element={<FinancePage />} />
              <Route path="/claims/:id" element={<ClaimDetailPage />} />
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
