"use client";
import { useState } from "react";
import { apiFetch } from "@/lib/api";

export default function ImportPage() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<any>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({ name: "" });
  const [extras, setExtras] = useState<Record<string, string>>({});
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function upload() {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await apiFetch<any>("/api/v1/students/import/preview", { method: "POST", body: fd as any });
      setPreview(r);
      setStep(2);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function doImport() {
    if (!file || !mapping.name) {
      setError("Map the 'name' column to continue.");
      return;
    }
    setBusy(true); setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("mapping", JSON.stringify({ ...mapping, extra_columns: extras }));
      fd.append("rows", "process_all");
      const r = await apiFetch<any>("/api/v1/students/import", { method: "POST", body: fd as any });
      setResult(r);
      setStep(3);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold">Import students</h1>
      <ol className="flex items-center gap-2 text-sm">
        <Step n={1} current={step} label="Upload" />
        <Sep />
        <Step n={2} current={step} label="Map columns" />
        <Sep />
        <Step n={3} current={step} label="Result" />
      </ol>

      {step === 1 && (
        <div className="card p-6">
          <label className="mb-2 block text-sm font-medium">Upload .xlsx</label>
          <input type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] || null)} className="block w-full text-sm" />
          <div className="mt-3 flex justify-end">
            <button className="btn-primary" disabled={!file || busy} onClick={upload}>{busy ? "Uploading…" : "Upload & preview"}</button>
          </div>
        </div>
      )}

      {step === 2 && preview && (
        <div className="card p-4">
          <p className="mb-3 text-sm text-muted">Detected {preview.row_count} rows. Drag each canonical field onto a column letter.</p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h3 className="mb-1 text-sm font-medium">Spreadsheet columns</h3>
              <div className="space-y-1 rounded border border-border p-2 text-sm">
                {preview.columns.map((c: any) => (
                  <div key={c.letter} className="rounded border border-border bg-surface2 px-2 py-1">
                    <strong>{c.letter}.</strong> {c.header || "(no header)"}{" "}
                    <span className="text-xs text-muted">— {c.sample_values?.slice(0, 3).join(", ")}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <FieldRow label="name *" value={mapping.name} onChange={(v: string) => setMapping({ ...mapping, name: v })} columns={preview.columns} required />
              <FieldRow label="student_code" value={mapping.student_code} onChange={(v: string) => setMapping({ ...mapping, student_code: v })} columns={preview.columns} />
              <FieldRow label="email" value={mapping.email} onChange={(v: string) => setMapping({ ...mapping, email: v })} columns={preview.columns} />
              <h3 className="text-sm font-medium">Extra columns</h3>
              <p className="text-xs text-muted">Map additional columns to preserve as student.extra_columns.</p>
              {preview.columns.map((c: any) => {
                if ([mapping.name, mapping.student_code, mapping.email].includes(c.letter)) return null;
                return (
                  <div key={c.letter} className="flex items-center gap-2 text-sm">
                    <span className="w-32 text-muted">{c.letter}. {c.header}</span>
                    <input
                      placeholder="extra key"
                      className="input flex-1"
                      value={Object.keys(extras).find((k) => extras[k] === c.letter) || ""}
                      onChange={(e) => {
                        const newExtras: any = { ...extras };
                        // remove existing mapping for this letter
                        Object.keys(newExtras).forEach((k) => { if (newExtras[k] === c.letter) delete newExtras[k]; });
                        if (e.target.value) newExtras[e.target.value] = c.letter;
                        setExtras(newExtras);
                      }}
                    />
                  </div>
                );
              })}
            </div>
          </div>
          {error && <div className="mt-2 text-xs text-danger">{error}</div>}
          <div className="mt-4 flex justify-between">
            <button className="btn-secondary" onClick={() => setStep(1)}>Back</button>
            <button className="btn-primary" disabled={busy} onClick={doImport}>{busy ? "Importing…" : "Import"}</button>
          </div>
        </div>
      )}

      {step === 3 && result && (
        <div className="card p-6">
          <h2 className="mb-2 text-base font-semibold">Imported {result.imported} students</h2>
          {result.skipped ? <p className="text-sm text-warning">Skipped {result.skipped}</p> : <p className="text-sm text-success">No errors.</p>}
          {result.errors?.length ? (
            <ul className="mt-2 text-xs text-danger">
              {result.errors.slice(0, 10).map((e: any, i: number) => (
                <li key={i}>Row {e.row}: {e.message}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </div>
  );
}

function Step({ n, current, label }: any) {
  const active = current === n;
  const done = current > n;
  return (
    <li className={`rounded-full px-3 py-1 ${active ? "bg-primary text-white" : done ? "bg-success text-white" : "bg-surface2 text-muted"}`}>
      {n}. {label}
    </li>
  );
}
function Sep() { return <span className="text-muted">→</span>; }
function FieldRow({ label, value, onChange, columns, required }: any) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-32 font-medium">{label}</span>
      <select className="input flex-1" value={value || ""} onChange={(e) => onChange(e.target.value)}>
        <option value="">— select column —</option>
        {columns.map((c: any) => (
          <option key={c.letter} value={c.letter}>{c.letter}. {c.header || "(no header)"}</option>
        ))}
      </select>
    </div>
  );
}
