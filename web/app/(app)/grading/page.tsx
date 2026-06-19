"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { EmptyState, StatusBadge } from "@/components/ui";

export default function GradingPage() {
  const list = useQuery({ queryKey: ["runs"], queryFn: () => apiFetch<any>("/api/v1/grading-runs") });
  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Grading runs</h1>
        <Link href="/grading/new" className="btn-primary">+ New grading run</Link>
      </div>
      {list.data?.data?.length ? (
        <div className="card overflow-hidden">
          <table>
            <thead><tr><th>Title</th><th>Status</th><th>Items</th><th>Flagged</th><th>Created</th></tr></thead>
            <tbody>
              {list.data.data.map((r: any) => (
                <tr key={r.id}>
                  <td><Link href={`/grading/${r.id}`} className="font-medium hover:underline">{r.title}</Link></td>
                  <td><StatusBadge status={r.status} /></td>
                  <td>{r.item_count}</td>
                  <td>{r.flagged_count ? <span className="badge-warning">{r.flagged_count}</span> : 0}</td>
                  <td className="text-muted">{new Date(r.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : !list.isLoading && <EmptyState title="No grading runs yet" action={{ label: "+ New grading run", onClick: () => location.assign("/grading/new") }} />}
    </div>
  );
}
