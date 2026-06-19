"use client";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { apiFetch } from "@/lib/api";

export default function NewGradingPage() {
  const router = useRouter();
  const sp = useSearchParams();
  const prefilledExamId = sp.get("exam_id") || "";
  const exams = useQuery({ queryKey: ["exams"], queryFn: () => apiFetch<any>("/api/v1/exams") });
  const [examId, setExamId] = useState(prefilledExamId);
  const [title, setTitle] = useState("Period 3 grading");
  const [benchmarkKind, setBenchmarkKind] = useState<"exam_answer_key" | "uploaded">("exam_answer_key");
  const [studentIds, setStudentIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const students = useQuery({ queryKey: ["students"], queryFn: () => apiFetch<any>("/api/v1/students") });

  const create = useMutation({
    mutationFn: () => apiFetch<any>("/api/v1/grading-runs", {
      method: "POST",
      body: JSON.stringify({ exam_id: examId, title, benchmark_kind: benchmarkKind, student_ids: studentIds }),
    }),
    onSuccess: (r) => router.push(`/grading/${r.id}`),
    onError: (e: any) => setError(e.message),
  });

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-2xl font-semibold">New grading run</h1>
      <div className="card p-5 space-y-3">
        <div>
          <label className="mb-1 block text-sm font-medium">Exam</label>
          <select className="input" value={examId} onChange={(e) => setExamId(e.target.value)}>
            <option value="">— select —</option>
            {exams.data?.data?.map((e: any) => <option key={e.id} value={e.id}>{e.title}</option>)}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Title</label>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Benchmark</label>
          <select className="input" value={benchmarkKind} onChange={(e) => setBenchmarkKind(e.target.value as any)}>
            <option value="exam_answer_key">Use AI-generated answer key</option>
            <option value="uploaded">Upload a benchmark (not supported in MVP wizard)</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Students</label>
          <div className="max-h-48 overflow-y-auto rounded border border-border p-2 text-sm">
            {students.data?.data?.map((s: any) => (
              <label key={s.id} className="flex items-center gap-2">
                <input type="checkbox" checked={studentIds.includes(s.id)} onChange={(e) => setStudentIds(e.target.checked ? [...studentIds, s.id] : studentIds.filter((x) => x !== s.id))} />
                {s.name} <span className="text-muted">{s.student_code}</span>
              </label>
            ))}
          </div>
        </div>
        {error && <div className="text-xs text-danger">{error}</div>}
        <div className="flex justify-end">
          <button className="btn-primary" disabled={!examId || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? "Creating…" : "Create run"}
          </button>
        </div>
      </div>
    </div>
  );
}
