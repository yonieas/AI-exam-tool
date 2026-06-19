"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { EmptyState, StatusBadge } from "@/components/ui";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function GradingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const run = useQuery({ queryKey: ["run", id], queryFn: () => apiFetch<any>(`/api/v1/grading-runs/${id}`), refetchInterval: 5000 });
  const items = useQuery({ queryKey: ["run", id, "items"], queryFn: () => apiFetch<any>(`/api/v1/grading-runs/${id}/items`), refetchInterval: 5000 });
  const students = useQuery({ queryKey: ["students"], queryFn: () => apiFetch<any>("/api/v1/students") });
  const [busyUpload, setBusyUpload] = useState<string | null>(null);

  async function uploadAnswer(itemId: string, studentId: string, file: File) {
    setBusyUpload(itemId);
    try {
      const presign = await apiFetch<any>("/api/v1/uploads/presign", {
        method: "POST",
        body: JSON.stringify({ kind: "student_answer", grading_run_id: id, filename: file.name, mime_type: file.type, size_bytes: file.size }),
      });
      const put = await fetch(presign.upload_url, { method: "PUT", body: file, headers: presign.headers });
      if (!put.ok) throw new Error("Upload failed");
      const fa = await apiFetch<any>(`/api/v1/grading-runs/${id}/files`, {
        method: "POST",
        body: JSON.stringify({ kind: "student_answer", storage_key: presign.storage_key, original_name: file.name, mime_type: file.type, size_bytes: file.size }),
      });
      await apiFetch(`/api/v1/grading-runs/${id}/items?Idempotency-Key=${crypto.randomUUID()}`, {
        method: "POST",
        body: JSON.stringify({ student_id: studentId, file_asset_id: fa.id }),
      });
      qc.invalidateQueries({ queryKey: ["run", id, "items"] });
    } finally {
      setBusyUpload(null);
    }
  }

  async function waive(itemId: string) {
    await apiFetch(`/api/v1/grading-runs/${id}/items/${itemId}/waive-flag`, { method: "POST" });
    qc.invalidateQueries({ queryKey: ["run", id, "items"] });
    qc.invalidateQueries({ queryKey: ["run", id] });
  }

  async function finalize() {
    try {
      await apiFetch(`/api/v1/grading-runs/${id}/finalize`, { method: "POST" });
      qc.invalidateQueries({ queryKey: ["run", id] });
    } catch (e: any) { alert(e.message); }
  }

  function downloadCsv() {
    window.location.href = `${API_BASE}/api/v1/grading-runs/${id}/results.csv`;
  }

  const flagged = items.data?.data?.filter((it: any) => it.flagged).length ?? 0;
  const canFinalize = run.data?.status !== "finalized" && flagged === 0 && (items.data?.data?.length || 0) > 0;

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{run.data?.title || "…"}</h1>
          <div className="text-sm text-muted">Status: <StatusBadge status={run.data?.status || "draft"} /> · Items: {run.data?.item_count || 0} · Flagged: {flagged}</div>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" disabled={run.data?.status !== "finalized"} onClick={downloadCsv}>Results CSV</button>
          <button className="btn-primary" disabled={!canFinalize} onClick={finalize}>Finalize</button>
        </div>
      </div>

      {items.data?.data?.length ? (
        <div className="card overflow-hidden">
          <table>
            <thead><tr><th>Student</th><th>Status</th><th>Total</th><th>Max</th><th>Flagged</th><th>Actions</th></tr></thead>
            <tbody>
              {items.data.data.map((it: any) => (
                <tr key={it.id} className={it.flagged ? "bg-amber-50" : ""}>
                  <td>{it.student_name}</td>
                  <td><StatusBadge status={it.status} /></td>
                  <td>{it.total_score ?? "—"}</td>
                  <td>{it.max_score_total}</td>
                  <td>{it.flagged ? <span className="badge-warning">flagged</span> : ""}</td>
                  <td>
                    {it.status === "pending" || it.status === "ai_processing" ? (
                      <label className="btn-secondary cursor-pointer">
                        {busyUpload === it.id ? "Uploading…" : "Upload answer"}
                        <input type="file" className="hidden" accept="image/*,.pdf" onChange={(e) => {
                          const f = e.target.files?.[0]; if (f) uploadAnswer(it.id, it.student_id, f);
                        }} />
                      </label>
                    ) : (
                      <div className="flex gap-1">
                        {it.flagged && <button className="btn-secondary" onClick={() => waive(it.id)}>Waive</button>}
                        <a href={`/grading/${id}/items/${it.id}`} className="btn-secondary">Review</a>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : !items.isLoading && <EmptyState title="No items in this run" />}
    </div>
  );
}
