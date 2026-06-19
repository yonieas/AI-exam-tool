"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { EmptyState, Dialog } from "@/components/ui";

export default function ClassesPage() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["classes"], queryFn: () => apiFetch<any>("/api/v1/classes") });
  const subjects = useQuery({ queryKey: ["subjects"], queryFn: () => apiFetch<any>("/api/v1/subjects") });
  const [showNew, setShowNew] = useState(false);
  const [name, setName] = useState("");
  const [grade, setGrade] = useState<number | null>(null);
  const [subjectIds, setSubjectIds] = useState<string[]>([]);

  const create = useMutation({
    mutationFn: (body: any) => apiFetch("/api/v1/classes", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["classes"] });
      setShowNew(false);
      setName(""); setGrade(null); setSubjectIds([]);
    },
  });

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Classes</h1>
        <button className="btn-primary" onClick={() => setShowNew(true)}>+ New class</button>
      </div>

      {list.data?.data?.length ? (
        <div className="card overflow-hidden">
          <table>
            <thead><tr><th>Name</th><th>Grade</th><th>Subjects</th><th>Students</th></tr></thead>
            <tbody>
              {list.data.data.map((c: any) => (
                <tr key={c.id}>
                  <td className="font-medium">{c.name}</td>
                  <td>{c.grade_level ?? "—"}</td>
                  <td>{c.subject_ids?.length || 0}</td>
                  <td>{c.student_count ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : !list.isLoading && <EmptyState title="No classes yet" action={{ label: "+ New class", onClick: () => setShowNew(true) }} />}

      <Dialog open={showNew} onClose={() => setShowNew(false)} title="New class"
        footer={
          <>
            <button className="btn-secondary" onClick={() => setShowNew(false)}>Cancel</button>
            <button className="btn-primary" disabled={!name || create.isPending} onClick={() => create.mutate({ name, grade_level: grade, subject_ids: subjectIds })}>
              {create.isPending ? "Saving…" : "Create"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium">Name *</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Grade 10-A" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Grade level</label>
            <input className="input" type="number" value={grade ?? ""} onChange={(e) => setGrade(e.target.value ? Number(e.target.value) : null)} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Subjects</label>
            <div className="space-y-1 rounded border border-border p-2">
              {subjects.data?.data?.map((s: any) => (
                <label key={s.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={subjectIds.includes(s.id)}
                    onChange={(e) => setSubjectIds(e.target.checked ? [...subjectIds, s.id] : subjectIds.filter((x) => x !== s.id))}
                  />
                  {s.name}
                </label>
              ))}
            </div>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
