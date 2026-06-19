"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { EmptyState, Dialog, StatusBadge } from "@/components/ui";

export default function SubjectsPage() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["subjects"], queryFn: () => apiFetch<any>("/api/v1/subjects") });
  const [showNew, setShowNew] = useState(false);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const create = useMutation({
    mutationFn: (body: any) => apiFetch("/api/v1/subjects", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["subjects"] });
      setShowNew(false);
      setName("");
      setCode("");
    },
  });

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Subjects</h1>
        <button className="btn-primary" onClick={() => setShowNew(true)}>+ New subject</button>
      </div>

      {list.data?.data?.length ? (
        <div className="card overflow-hidden">
          <table>
            <thead><tr><th>Name</th><th>Code</th><th>Status</th></tr></thead>
            <tbody>
              {list.data.data.map((s: any) => (
                <tr key={s.id}>
                  <td className="font-medium">{s.name}</td>
                  <td className="text-muted">{s.code || "—"}</td>
                  <td>{s.deleted_at ? "deleted" : "active"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        !list.isLoading && <EmptyState title="No subjects yet" description="Add the subjects you teach." action={{ label: "+ New subject", onClick: () => setShowNew(true) }} />
      )}

      <Dialog open={showNew} onClose={() => setShowNew(false)} title="New subject"
        footer={
          <>
            <button className="btn-secondary" onClick={() => setShowNew(false)}>Cancel</button>
            <button className="btn-primary" disabled={!name || create.isPending} onClick={() => create.mutate({ name, code: code || null })}>
              {create.isPending ? "Saving…" : "Create"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium">Name *</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Physics" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Code</label>
            <input className="input" value={code} onChange={(e) => setCode(e.target.value)} placeholder="PHYS" />
          </div>
          {create.error && <div className="text-xs text-danger">{(create.error as any).message}</div>}
        </div>
      </Dialog>
    </div>
  );
}
