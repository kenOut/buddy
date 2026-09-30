"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, api, resolveAvatarUrl } from "@/lib/api";
import type { Employee } from "@/lib/types";

const MAX_BYTES = 5 * 1024 * 1024;
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];

function initials(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .filter(Boolean)
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

/**
 * Client island inside the (server-rendered) employee detail page — file
 * upload needs real interactivity, so just this control is a client
 * component rather than the whole page. Posts straight to
 * POST /employees/{id}/avatar (multipart), then router.refresh() to pull
 * the server component's data again so the rest of the page (which also
 * shows this employee) sees the new avatar_url too.
 */
export function EmployeeAvatarUpload({ employee }: { employee: Employee }) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [avatarUrl, setAvatarUrl] = useState(employee.avatar_url);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const resolvedUrl = resolveAvatarUrl(avatarUrl);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file after an error
    if (!file) return;

    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError("Use a JPEG, PNG, WebP, or GIF image.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("Image must be 5MB or smaller.");
      return;
    }

    setError(null);
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const updated = await api.upload<Employee>(`/employees/${employee.id}/avatar`, formData);
      setAvatarUrl(updated.avatar_url);
      setFailed(false);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? "Couldn't upload that image." : "Network error — try again.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="flex items-center gap-3">
      {resolvedUrl && !failed ? (
        // eslint-disable-next-line @next/next/no-img-element -- backend-served photo, not a static build asset.
        <img
          key={resolvedUrl}
          src={resolvedUrl}
          alt={employee.full_name}
          className="h-14 w-14 rounded-full object-cover ring-2 ring-buddy-border"
          onError={() => setFailed(true)}
        />
      ) : (
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-buddy-primary/10 text-lg font-semibold text-buddy-primary">
          {initials(employee.full_name)}
        </div>
      )}

      <div className="flex flex-col items-start gap-1">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="text-xs font-medium text-buddy-primary underline-offset-2 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
        >
          {uploading ? "Uploading…" : resolvedUrl ? "Change photo" : "Upload photo"}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(",")}
          onChange={handleFileChange}
          className="hidden"
        />
        {error && (
          <p role="alert" className="text-xs text-red-600 dark:text-red-400">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
