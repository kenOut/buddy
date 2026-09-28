import { api, ApiError } from "@/lib/api";

export interface AdminSessionStatus {
  authenticated: boolean;
}

export async function checkAdminSession(): Promise<boolean> {
  const status = await api.get<AdminSessionStatus>("/admin/session");
  return status.authenticated;
}

export async function adminLogin(password: string): Promise<void> {
  try {
    await api.post<AdminSessionStatus>("/admin/login", { password });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      throw new Error("Incorrect password.");
    }
    throw err;
  }
}

export async function adminLogout(): Promise<void> {
  await api.post<AdminSessionStatus>("/admin/logout");
}
