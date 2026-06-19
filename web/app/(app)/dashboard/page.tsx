"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { apiFetch } from "@/lib/api";

export default function DashboardPage() {
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => apiFetch<any>("/api/v1/me/dashboard") });
  const exams = useQuery({ queryKey: ["exams", "recent"], queryFn: () => apiFetch<any>("/api/v1/exams?limit=5") });
  const runs = useQuery({ queryKey: ["runs", "recent"], queryFn: () => apiFetch<any>("/api/v1/grading-runs?limit=5") });

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <h1 className="text-2xl font-semibold">Welcome back</h1>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <StatCard label="Subjects" value={dash.data?.subjects} loading={dash.isLoading} />
        <StatCard label="Classes" value={dash.data?.classes} loading={dash.isLoading} />
        <StatCard label="Students" value={dash.data?.students} loading={dash.isLoading} />
        <StatCard label="Exams" value={dash.data?.exams} loading={dash.isLoading} />
        <StatCard label="Grading runs" value={dash.data?.grading_runs} loading={dash.isLoading} />
        <StatCard label="Flagged items" value={dash.data?.flagged_items} loading={dash.isLoading} tone="warning" />
      </div>

      <div className="flex gap-2">
        <Link href="/exams/new" className="btn-primary">+ New exam</Link>
        <Link href="/students/import" className="btn-secondary">Import students</Link>
        <Link href="/grading/new" className="btn-secondary">+ New grading run</Link>
      </div>

      <section className="card p-4">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">Recent exams</h2>
        {exams.isLoading ? <div className="text-muted">Loading…</div> : (
          <ul className="divide-y divide-border">
            {exams.data?.data?.length ? exams.data.data.map((e: any) => (
              <li key={e.id} className="flex items-center justify-between py-2">
                <Link href={`/exams/${e.id}`} className="text-sm font-medium hover:underline">{e.title}</Link>
                <StatusBadge status={e.status} />
              </li>
            )) : <li className="py-2 text-sm text-muted">No exams yet — create one above.</li>}
          </ul>
        )}
      </section>

      <section className="card p-4">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">Recent grading runs</h2>
        {runs.isLoading ? <div className="text-muted">Loading…</div> : (
          <ul className="divide-y divide-border">
            {runs.data?.data?.length ? runs.data.data.map((r: any) => (
              <li key={r.id} className="flex items-center justify-between py-2">
                <Link href={`/grading/${r.id}`} className="text-sm font-medium hover:underline">{r.title}</Link>
                <StatusBadge status={r.status} />
              </li>
            )) : <li className="py-2 text-sm text-muted">No grading runs yet.</li>}
          </ul>
        )}
      </section>
    </div>
  );
}

function StatCard({ label, value, loading, tone }: any) {
  const toneClass = tone === "warning" ? "text-warning" : "text-text";
  return (
    <div className="card p-4">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${toneClass}`}>{loading ? "—" : (value ?? 0)}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls: Record<string, string> = {
    draft: "badge-neutral", in_review: "badge-info", published: "badge-success",
    closed: "badge-neutral", grading: "badge-warning", needs_review: "badge-warning", finalized: "badge-success",
    done: "badge-success", failed: "badge-danger", queued: "badge-info", processing: "badge-warning",
  };
  return <span className={cls[status] || "badge-neutral"}>{status}</span>;
}
