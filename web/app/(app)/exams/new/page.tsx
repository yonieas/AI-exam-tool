"use client";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function NewExamPage() {
  const router = useRouter();
  const subjects = useQuery({ queryKey: ["subjects"], queryFn: () => apiFetch<any>("/api/v1/subjects") });
  const [step, setStep] = useState(1);
  const [subjectId, setSubjectId] = useState<string>("");
  const [title, setTitle] = useState("");
  const [units, setUnits] = useState<string[]>([]);
  const [unitInput, setUnitInput] = useState("");
  const [mode, setMode] = useState<"mcq" | "essay" | "both">("both");
  const [total, setTotal] = useState(5);
  const [mcq, setMcq] = useState(3);
  const [essay, setEssay] = useState(2);
  const [sourceFile, setSourceFile] = useState<{ id: string; name: string } | null>(null);
  const [examId, setExamId] = useState<string | null>(null);
  const [job, setJob] = useState<any>(null);
  const [questions, setQuestions] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => apiFetch<any>("/api/v1/exams", {
      method: "POST",
      body: JSON.stringify({
        subject_id: subjectId, title, units,
        question_type_mode: mode, total_count: total,
        mcq_count: mode === "mcq" ? total : (mode === "both" ? mcq : null),
        essay_count: mode === "essay" ? total : (mode === "both" ? essay : null),
        source: sourceFile ? { kind: "image", file_asset_id: sourceFile.id } : undefined,
      }),
    }),
    onSuccess: (e) => {
      setExamId(e.id);
      setStep(5);
      doGenerate(e.id);
    },
    onError: (e: any) => setError(e.message),
  });

  async function doGenerate(id: string) {
    setError(null);
    const r = await apiFetch<any>(`/api/v1/exams/${id}/generate?Idempotency-Key=${crypto.randomUUID()}`, { method: "POST" });
    setJob(r.ai_job);
    pollUntilDone(r.ai_job.id, id);
  }

  async function pollUntilDone(jobId: string, eid: string) {
    for (let i = 0; i < 60; i++) {
      await new Promise((r) => setTimeout(r, 700));
      try {
        const r = await apiFetch<any>(`/api/v1/ai-jobs/${jobId}`);
        if (r.job_status === "done") {
          const qs = await apiFetch<any>(`/api/v1/exams/${eid}/questions`);
          setQuestions(qs.data || []);
          setStep(6);
          return;
        }
        if (r.job_status === "failed") {
          setError(r.error || "AI generation failed.");
          return;
        }
      } catch (e: any) {
        // ignore and retry
      }
    }
  }

  async function uploadSource(file: File) {
    const presign = await apiFetch<any>("/api/v1/uploads/presign", {
      method: "POST",
      body: JSON.stringify({ kind: "source_image", filename: file.name, mime_type: file.type, size_bytes: file.size }),
    });
    await fetch(presign.upload_url, { method: "PUT", body: file, headers: presign.headers });
    // We need an exam_id before registering the file, so we will create the file asset after the exam is created
    // For simplicity, we skip the file_asset registration here and let the user attach it after publish.
    return { id: "pending", name: file.name, storage_key: presign.storage_key, mime_type: file.type };
  }

  async function approveAll() {
    if (!examId) return;
    for (const q of questions) {
      await apiFetch(`/api/v1/exams/${examId}/questions/${q.id}/approve`, { method: "POST" });
    }
    await apiFetch(`/api/v1/exams/${examId}/publish`, { method: "POST" });
    router.push(`/exams/${examId}`);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold">New exam</h1>
      <ol className="flex gap-2 text-sm">
        {["Subject", "Title", "Counts", "Source", "Generate", "Review", "Publish"].map((label, i) => (
          <li key={i} className={`rounded-full px-3 py-1 ${step === i + 1 ? "bg-primary text-white" : step > i + 1 ? "bg-success text-white" : "bg-surface2 text-muted"}`}>
            {i + 1}. {label}
          </li>
        ))}
      </ol>

      <div className="card p-5">
        {step === 1 && (
          <div className="space-y-3">
            <label className="block text-sm font-medium">Pick a subject</label>
            <select className="input" value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
              <option value="">— select —</option>
              {subjects.data?.data?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            {error && <div className="text-xs text-danger">{error}</div>}
            <div className="flex justify-end">
              <button className="btn-primary" disabled={!subjectId} onClick={() => setStep(2)}>Next</button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Title *</label>
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Physics Unit 1" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Units</label>
              <div className="flex flex-wrap gap-1">
                {units.map((u, i) => (
                  <span key={i} className="badge-info cursor-pointer" onClick={() => setUnits(units.filter((_, x) => x !== i))}>{u} ✕</span>
                ))}
              </div>
              <div className="mt-2 flex gap-2">
                <input className="input" value={unitInput} onChange={(e) => setUnitInput(e.target.value)} placeholder="e.g. Kinematics" />
                <button className="btn-secondary" onClick={() => { if (unitInput) { setUnits([...units, unitInput]); setUnitInput(""); } }}>Add</button>
              </div>
            </div>
            <div className="flex justify-between">
              <button className="btn-secondary" onClick={() => setStep(1)}>Back</button>
              <button className="btn-primary" disabled={!title} onClick={() => setStep(3)}>Next</button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Mode</label>
              <select className="input" value={mode} onChange={(e) => setMode(e.target.value as any)}>
                <option value="mcq">All MCQ</option>
                <option value="essay">All essay</option>
                <option value="both">Mixed</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Total questions *</label>
              <input className="input" type="number" min={1} max={100} value={total} onChange={(e) => setTotal(Number(e.target.value))} />
            </div>
            {mode === "both" && (
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-sm font-medium">MCQ count</label>
                  <input className="input" type="number" min={0} value={mcq} onChange={(e) => setMcq(Number(e.target.value))} />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">Essay count</label>
                  <input className="input" type="number" min={0} value={essay} onChange={(e) => setEssay(Number(e.target.value))} />
                </div>
                <div className="col-span-2 text-xs text-muted">MCQ + essay must equal total ({mcq + essay} / {total})</div>
              </div>
            )}
            <div className="flex justify-between">
              <button className="btn-secondary" onClick={() => setStep(2)}>Back</button>
              <button className="btn-primary" disabled={total < 1 || (mode === "both" && mcq + essay !== total)} onClick={() => setStep(4)}>Next</button>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-3">
            <label className="block text-sm font-medium">Source (optional)</label>
            <input type="file" accept="image/*,.pdf" onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const u = await uploadSource(f);
              setSourceFile({ id: u.name, name: u.name });
            }} className="block w-full text-sm" />
            {sourceFile && <div className="text-xs text-muted">Selected: {sourceFile.name}</div>}
            {error && <div className="text-xs text-danger">{error}</div>}
            <div className="flex justify-between">
              <button className="btn-secondary" onClick={() => setStep(3)}>Back</button>
              <button className="btn-primary" onClick={() => { setStep(5); create.mutate(); }}>Generate</button>
            </div>
          </div>
        )}

        {step === 5 && (
          <div className="space-y-3 text-center">
            <div className="text-sm">⏳ Generating questions…</div>
            <div className="text-xs text-muted">Job: {job?.id?.slice(0, 8)}… — {job?.job_status}</div>
          </div>
        )}

        {step === 6 && (
          <div className="space-y-3">
            <h2 className="text-base font-semibold">Review questions ({questions.length})</h2>
            <ul className="space-y-2">
              {questions.map((q) => (
                <li key={q.id} className="card p-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-xs text-muted">Q{q.position} · {q.type}</span>
                      <p className="text-sm">{q.prompt}</p>
                    </div>
                    <span className="badge-warning">{q.status}</span>
                  </div>
                </li>
              ))}
            </ul>
            <div className="flex justify-end gap-2">
              <button className="btn-primary" onClick={approveAll}>Approve all & publish</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
