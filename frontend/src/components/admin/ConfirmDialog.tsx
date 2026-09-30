"use client";
import { useEffect } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  tone = "default",
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  tone?: "default" | "danger";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-buddy-overlay px-4 backdrop-blur-[2px]"
      onClick={onCancel}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-desc"
        className="w-full max-w-sm"
        onClick={(e) => e.stopPropagation()}
      >
        <Card>
          <h2 id="confirm-title" className="text-lg font-semibold text-foreground">{title}</h2>
          <p id="confirm-desc" className="mt-1 text-sm text-buddy-muted">{description}</p>
          <div className="mt-5 flex justify-end gap-2">
            <Button type="button" variant="secondary" autoFocus onClick={onCancel} disabled={busy}>
              Cancel
            </Button>
            <Button type="button" variant={tone === "danger" ? "danger" : "primary"} onClick={onConfirm} disabled={busy}>
              {busy ? "Working…" : confirmLabel}
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
