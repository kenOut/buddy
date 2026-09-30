"use client";
import Link from "next/link";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";

export default function EmployeeError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="space-y-4">
      <Link href="/admin/employees" className="text-sm text-buddy-muted hover:text-foreground">← Back to employees</Link>
      <EmptyState
        title="We couldn't load this employee"
        description="The backend may be unreachable. Try again in a moment."
        action={<Button onClick={reset}>Try again</Button>}
      />
    </div>
  );
}
