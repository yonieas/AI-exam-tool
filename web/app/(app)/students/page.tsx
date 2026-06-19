"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { EmptyState, Dialog } from "@/components/ui";

export default function StudentsPage() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["students"], queryFn: () => apiFetch<any>("/api/v1/students") });
  const [showNew, setShowNew] = useState(false);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [email, setEmail] = useState("");

  const create = useMutation({
    mutationFn: (body: any) => apiFetch("/api/v1/students", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["students"] });
      setShowNew(false); setName(""); setCode(""); setEmail("");
    },
  });

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Students</h1>
        <div className="flex gap-2">
          <Link href="/students/import" className="btn-secondary">Import Excel</Link>
          <button className="btn-primary" onClick={() => setShowNew(true)}>+ Add student</button>
        </div>
      </div>

      {list.data?.data?.length ? (
        <div className="card overflow-hidden">
          <table>
            <thead><tr><th>Name</th><th>Code</th><th>Email</th><th>Extras</th></tr></thead>
            <tbody>
              {list.data.data.map((s: any) => (
                <tr key={s.id}>
                  <td className="font-medium">{s.name}</td>
                  <td className="text-muted">{s.student_code || "—"}</td>
                  <td className="text-muted">{s.email || "—"}</td>
                  <td className="text-xs text-muted">
                    {s.extra_columns && Object.keys(s.extra_columns).length
                      ? Object.entries(s.extra_columns).map(([k, v]: any) => `${k}: ${v}`).join("; ")
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : !list.isLoading && <EmptyState title="No students yet" action={{ label: "+ Add student", onClick: () => setShowNew(true) }} />}

      <Dialog open={showNew} onClose={() => setShowNew(false)} title="New student"
        footer={
          <>
            <button className="btn-secondary" onClick={() => setShowNew(false)}>Cancel</button>
            <button className="btn-primary" disabled={!name || create.isPending} onClick={() => create.mutate({ name, student_code: code || null, email: email || null })}>
              {create.isPending ? "Saving…" : "Create"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium">Name *</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Student code</label>
            <input className="input" value={code} onChange={(e) => setCode(e.target.value)} placeholder="S001" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Email</label>
            <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
        </div>
      </Dialog>
    </div>
  );
}
