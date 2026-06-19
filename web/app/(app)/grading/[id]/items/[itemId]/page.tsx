"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { StatusBadge } from "@/components/ui";

export default function GradingItemPage() {
  const { id, itemId } = useParams<{ id: string; itemId: string }>();
  const qc = useQueryClient();
  const item = useQuery({ queryKey: ["item", itemId], queryFn: () => apiFetch<any>(`/api/v1/grading-runs/${id}/items/${itemId}`) });
  const [edits, setEdits] = useState<Record<string, { score: string; rationale: string }>>({});

  const saveOverride = useMutation({
    mutationFn: ({ rid, score, rationale }: any) => apiFetch(`/api/v1/grading-runs/${id}/items/${itemId}/responses/${rid}`, {
      method: "PATCH",
      body: JSON.stringify({ teacher_score: Number(score), teacher_rationale: rationale || null }),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["item", itemId] }),
  });

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">{item.data?.student_name || "…"}</h1>
        <div className="text-sm text-muted">
          <StatusBadge status={item.data?.status || ""} /> · Total: {item.data?.total_score ?? "—"} / {item.data?.max_score_total}
        </div>
      </div>

      <div className="card overflow-hidden">
        <table>
          <thead>
            <tr>
              <th>#</th><th>Prompt</th><th>AI</th><th>Max</th><th>Conf</th><th>Flag</th><th>Rationale</th><th>Teacher score</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {item.data?.responses?.map((r: any) => {
              const e = edits[r.id] || { score: r.teacher_score ?? "", rationale: r.teacher_rationale ?? "" };
              return (
                <tr key={r.id}>
                  <td>Q{r.question_position}</td>
                  <td className="max-w-md">{r.question_prompt}</td>
                  <td>{r.ai_score ?? "—"}</td>
                  <td>{r.max_score}</td>
                  <td>{r.confidence ?? "—"}</td>
                  <td>{r.flagged ? <span className="badge-warning">flag</span> : ""}</td>
                  <td className="text-xs text-muted">{r.ai_rationale}</td>
                  <td>
                    <input
                      type="number" min={0} max={r.max_score} step="0.1"
                      className="input w-24"
                      value={e.score}
                      onChange={(ev) => setEdits({ ...edits, [r.id]: { ...e, score: ev.target.value } })}
                    />
                  </td>
                  <td>
                    <button className="btn-secondary" onClick={() => saveOverride.mutate({ rid: r.id, ...e })}>
                      Save
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
