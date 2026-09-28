"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { Sidebar } from "@/components/admin/Sidebar";
import { checkAdminSession } from "@/lib/adminAuth";

type Status = "checking" | "authenticated" | "unauthenticated";

export function AdminAuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isLoginRoute = pathname === "/admin/login";
  const [status, setStatus] = useState<Status>(isLoginRoute ? "authenticated" : "checking");

  useEffect(() => {
    if (isLoginRoute) return;

    let cancelled = false;
    checkAdminSession()
      .then((authenticated) => {
        if (cancelled) return;
        if (authenticated) {
          setStatus("authenticated");
        } else {
          setStatus("unauthenticated");
          router.replace("/admin/login");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatus("unauthenticated");
          router.replace("/admin/login");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isLoginRoute, pathname, router]);

  // The login page itself renders standalone — no sidebar chrome, no
  // session check (checking it here would just bounce back to itself).
  if (isLoginRoute) {
    return <>{children}</>;
  }

  if (status !== "authenticated") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-buddy-cloud">
        <p className="text-sm text-buddy-muted">Checking session…</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col sm:flex-row">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-y-auto p-4 sm:p-8">{children}</main>
    </div>
  );
}
