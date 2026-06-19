"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { EmptyState, StatusBadge } from "@/components/ui";

export default function ExamsPage() {
  const [q, setQ] = useState("");
  const list = useQuery({ queryKey: ["exams", q], queryFn: () => apiFetch<any>(`/api/v1/exams?q=${encodeURIComponent(q)}`) });

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Exams</h1>
        <Link href="/exams/new" className="btn-primary">+ New exam</Link>
      </div>
      <div className="flex gap-2">
        <input className="input" placeholder="Search by title…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {list.data?.data?.length ? (
        <div className="card overflow-hidden">
          <table>
            <thead><tr><th>Title</th><th>Status</th><th>Questions</th><th>Created</th></tr></thead>
            <tbody>
              {list.data.data.map((e: any) => (
                <tr key={e.id}>
                  <td><Link href={`/exams/${e.id}`} className="font-medium hover:underline">{e.title}</Link></td>
                  <td><StatusBadge status={e.status} /></td>
                  <td>{e.question_count ?? 0}</td>
                  <td className="text-muted">{new Date(e.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : !list.isLoading && <EmptyState title="No exams yet" description="Create your first exam." action={{ label: "+ New exam", onClick: () => location.assign("/exams/new") }} />}
    </div>
  );
}
