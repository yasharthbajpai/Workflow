import { api } from "./client";
import type {
  Claim,
  ClaimDetail,
  DashboardSummary,
  DocumentOut,
  Employee,
  LoginResponse,
  TravelRequest,
} from "../types";

export const AuthApi = {
  login: (email: string, password: string) =>
    api.post<LoginResponse>("/auth/login", { email, password }).then((r) => r.data),
  me: () => api.get<Employee>("/auth/me").then((r) => r.data),
  demoUsers: () => api.get<Employee[]>("/auth/demo-users").then((r) => r.data),
};

export const EmployeesApi = {
  list: () => api.get<Employee[]>("/employees").then((r) => r.data),
};

export const TravelRequestsApi = {
  mine: () => api.get<TravelRequest[]>("/travel-requests/mine").then((r) => r.data),
  get: (id: number) => api.get<TravelRequest>(`/travel-requests/${id}`).then((r) => r.data),
  create: (payload: Partial<TravelRequest>) =>
    api.post<TravelRequest>("/travel-requests", payload).then((r) => r.data),
  documents: (id: number) => api.get<DocumentOut[]>(`/travel-requests/${id}/documents`).then((r) => r.data),
  scan: (id: number) => api.post<ClaimDetail>(`/travel-requests/${id}/scan`).then((r) => r.data),
};

export const ClaimsApi = {
  mine: () => api.get<Claim[]>("/claims/mine").then((r) => r.data),
  get: (id: number) => api.get<ClaimDetail>(`/claims/${id}`).then((r) => r.data),
  patchLine: (claimId: number, lineId: number, payload: Record<string, unknown>) =>
    api.patch<ClaimDetail>(`/claims/${claimId}/lines/${lineId}`, payload).then((r) => r.data),
  submit: (id: number) => api.post<ClaimDetail>(`/claims/${id}/submit`).then((r) => r.data),
  resubmit: (id: number) => api.post<ClaimDetail>(`/claims/${id}/resubmit`).then((r) => r.data),
};

export const ApprovalsApi = {
  myQueue: () => api.get<Claim[]>("/approvals/my-queue").then((r) => r.data),
  approve: (id: number, remarks?: string) =>
    api.post<ClaimDetail>(`/approvals/${id}/approve`, { remarks }).then((r) => r.data),
  reject: (id: number, remarks: string) =>
    api.post<ClaimDetail>(`/approvals/${id}/reject`, { remarks }).then((r) => r.data),
  return: (id: number, remarks: string) =>
    api.post<ClaimDetail>(`/approvals/${id}/return`, { remarks }).then((r) => r.data),
};

export const FinanceApi = {
  verificationQueue: () => api.get<Claim[]>("/finance/verification-queue").then((r) => r.data),
  paymentRun: () => api.get<Claim[]>("/finance/payment-run").then((r) => r.data),
  verify: (id: number) => api.post<ClaimDetail>(`/finance/${id}/verify`).then((r) => r.data),
  pay: (id: number, reference: string) =>
    api.post<ClaimDetail>(`/finance/${id}/pay`, { reference }).then((r) => r.data),
};

export const DashboardApi = {
  summary: () => api.get<DashboardSummary>("/dashboard/summary").then((r) => r.data),
};
