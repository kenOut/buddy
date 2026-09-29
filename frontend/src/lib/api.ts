const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
// The backend serves uploaded files (employee avatars) at /static/*, not
// under the versioned /api/v1 prefix API_BASE_URL points at — this is
// that same host with the API suffix stripped back off.
const API_ORIGIN = API_BASE_URL.replace(/\/api\/v\d+\/?$/, "");

/** `Employee.avatar_url` is either an already-absolute URL (seeded
 * placeholder photos) or a backend-relative path (an uploaded avatar,
 * e.g. "/static/avatars/<id>.jpg") — resolve the latter against the
 * API's own origin, not the frontend's, since that's where the file is
 * actually served from. */
export function resolveAvatarUrl(avatarUrl: string | null | undefined): string | null {
  if (!avatarUrl) return null;
  if (/^https?:\/\//i.test(avatarUrl)) return avatarUrl;
  return `${API_ORIGIN}${avatarUrl.startsWith("/") ? "" : "/"}${avatarUrl}`;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

async function upload<T>(path: string, formData: FormData): Promise<T> {
  // No explicit Content-Type here (unlike `request` above) — the browser
  // sets the multipart boundary itself from the FormData body, which a
  // hardcoded "application/json" would silently break.
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }

  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload,
};
