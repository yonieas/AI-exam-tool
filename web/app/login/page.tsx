"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, setAccessToken, setCurrentUser } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function loginDev(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await apiFetch<any>("/api/v1/auth/dev-login", {
        method: "POST",
        body: JSON.stringify({ email, full_name: name }),
      });
      setAccessToken(r.access_token);
      setCurrentUser(r.user);
      router.replace("/dashboard");
    } catch (e: any) {
      setError(e.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  function loginGoogle() {
    // In dev, the backend redirects to ?google_not_configured=1; in prod this is a real OAuth.
    window.location.href = `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"}/api/v1/auth/google`;
  }

  return (
    <main className="flex h-screen items-center justify-center bg-bg p-6">
      <div className="card w-full max-w-md p-6">
        <h1 className="mb-1 text-xl font-semibold">Teacher AI Exam Tool</h1>
        <p className="mb-4 text-sm text-muted">Sign in to continue.</p>

        <button className="btn-primary mb-3 w-full justify-center" onClick={loginGoogle} type="button">
          Continue with Google
        </button>

        <div className="my-3 flex items-center text-xs text-muted">
          <div className="flex-1 border-t border-border" />
          <span className="px-2">or use dev login</span>
          <div className="flex-1 border-t border-border" />
        </div>

        <form onSubmit={loginDev} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium">Email</label>
            <input
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="teacher@example.com"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ms. Alvarez" />
          </div>
          {error && <div className="text-xs text-danger">{error}</div>}
          <button type="submit" disabled={busy} className="btn-secondary w-full justify-center">
            {busy ? "Signing in…" : "Dev sign-in"}
          </button>
        </form>

        <p className="mt-4 text-center text-xs text-muted">By signing in, you agree to the terms.</p>
      </div>
    </main>
  );
}
