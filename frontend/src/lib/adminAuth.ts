import { api, ApiError } from "@/lib/api";

export interface AdminSessionStatus {
  authenticated: boolean;
}

export async function checkAdminSession(): Promise<boolean> {
  const status = await api.get<AdminSessionStatus>("/admin/session");
  return status.authenticated;
}

/** `email` omitted (or blank) signs in with the original shared
 * Manager Portal password; supplied, signs in as that specific
 * stakeholder account instead (see backend AdminLoginRequest's own
 * docstring) — both issue the same session. */
export async function adminLogin(password: string, email?: string): Promise<void> {
  try {
    await api.post<AdminSessionStatus>("/admin/login", email ? { email, password } : { password });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      throw new Error(email ? "Incorrect email or password." : "Incorrect password.");
    }
    throw err;
  }
}

export async function adminLogout(): Promise<void> {
  await api.post<AdminSessionStatus>("/admin/logout");
}
