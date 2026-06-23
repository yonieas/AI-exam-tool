"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, apiDownload } from "@/lib/api";
import { EmptyState, StatusBadge } from "@/components/ui";

export default function ExamDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const exam = useQuery({ queryKey: ["exam", id], queryFn: () => apiFetch<any>(`/api/v1/exams/${id}`) });
  const questions = useQuery({ queryKey: ["exam", id, "questions"], queryFn: () => apiFetch<any>(`/api/v1/exams/${id}/questions`) });
  const files = useQuery({ queryKey: ["exam", id, "files"], queryFn: () => apiFetch<any>(`/api/v1/exams/${id}/files`) });

  async function downloadPdf(kind: "questions" | "answers") {
    try {
      const r = await apiDownload(`/api/v1/exams/${id}/pdf/${kind}`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${exam.data?.title}_${kind}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) { alert(e.message || "Download failed"); }
  }

  async function downloadFile(file: any) {
    try {
      const r = await apiDownload(`/api/v1/exams/${id}/files/${file.id}/download`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.original_name;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) { alert(e.message || "Download failed"); }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{exam.data?.title || "…"}</h1>
          <div className="text-sm text-muted">{exam.data?.question_count || 0} questions · <StatusBadge status={exam.data?.status || "draft"} /></div>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" disabled={!exam.data?.questions_pdf_file_id} onClick={() => downloadPdf("questions")}>Questions PDF</button>
          <button className="btn-secondary" disabled={!exam.data?.answers_pdf_file_id} onClick={() => downloadPdf("answers")}>Answers PDF</button>
          <Link href={`/grading/new?exam_id=${id}`} className="btn-primary">Start grading run</Link>
        </div>
      </div>

      <section className="card p-4">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">Questions</h2>
        {questions.data?.data?.length ? (
          <ul className="space-y-2">
            {questions.data.data.map((q: any) => (
              <li key={q.id} className="rounded border border-border p-3">
                <div className="flex items-start justify-between">
                  <div>
                    <span className="text-xs text-muted">Q{q.position} · {q.type} · max {q.max_score} pts</span>
                    <p className="text-sm">{q.prompt}</p>
                  </div>
                  <StatusBadge status={q.status} />
                </div>
              </li>
            ))}
          </ul>
        ) : !questions.isLoading && <EmptyState title="No questions yet" />}
      </section>

      <section className="card p-4">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">Files</h2>
        {files.data?.data?.length ? (
          <ul className="space-y-1">
            {files.data.data.map((f: any) => (
              <li key={f.id} className="flex items-center justify-between rounded border border-border px-3 py-2">
                <div>
                  <div className="text-sm font-medium">{f.original_name}</div>
                  <div className="text-xs text-muted">{f.kind} · {Math.round((f.size_bytes || 0) / 1024 * 10) / 10} KB</div>
                </div>
                <button className="btn-secondary" onClick={() => downloadFile(f)}>Download</button>
              </li>
            ))}
          </ul>
        ) : !files.isLoading && <div className="text-sm text-muted">No files yet.</div>}
      </section>
    </div>
  );
}
