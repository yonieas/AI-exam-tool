"use client";
import { useState } from "react";

export function StatusBadge({ status }: { status: string }) {
  const cls: Record<string, string> = {
    draft: "badge-neutral", in_review: "badge-info", published: "badge-success",
    closed: "badge-neutral", grading: "badge-warning", needs_review: "badge-warning", finalized: "badge-success",
    done: "badge-success", failed: "badge-danger", queued: "badge-info", processing: "badge-warning",
    pending: "badge-neutral", ai_processing: "badge-info", ai_done: "badge-info", reviewed: "badge-success", final: "badge-success",
  };
  return <span className={cls[status] || "badge-neutral"}>{status.replace(/_/g, " ")}</span>;
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: { label: string; onClick: () => void } }) {
  return (
    <div className="card flex flex-col items-center gap-2 p-8 text-center">
      <div className="text-base font-medium">{title}</div>
      {description && <div className="text-sm text-muted">{description}</div>}
      {action && <button className="btn-primary mt-2" onClick={action.onClick}>{action.label}</button>}
    </div>
  );
}

export function Dialog({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; footer?: React.ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="card w-full max-w-lg p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-base font-semibold">{title}</h3>
          <button className="text-muted hover:text-text" onClick={onClose}>✕</button>
        </div>
        <div>{children}</div>
        {footer && <div className="mt-4 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({ open, onConfirm, onCancel, title, description, destructive, confirmLabel }: any) {
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      title={title}
      footer={
        <>
          <button className="btn-secondary" onClick={onCancel}>Cancel</button>
          <button className={destructive ? "btn-danger" : "btn-primary"} onClick={onConfirm}>{confirmLabel || "Confirm"}</button>
        </>
      }
    >
      <p className="text-sm text-muted">{description}</p>
    </Dialog>
  );
}
