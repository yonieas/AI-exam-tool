"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, bootstrapAuth, getCurrentUser, setAccessToken, setCurrentUser } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/subjects", label: "Subjects" },
  { href: "/classes", label: "Classes" },
  { href: "/students", label: "Students" },
  { href: "/exams", label: "Exams" },
  { href: "/grading", label: "Grading" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
    (async () => {
      const t = await bootstrapAuth();
      if (!t) {
        router.replace("/login");
        return;
      }
      try {
        const me = await apiFetch<any>("/api/v1/me");
        setUser(me);
      } catch {
        router.replace("/login");
        return;
      }
      setReady(true);
    })();
  }, [router]);

  async function logout() {
    try {
      await apiFetch("/api/v1/auth/logout", { method: "POST" });
    } catch {}
    setAccessToken(null);
    setCurrentUser(null);
    router.replace("/login");
  }

  if (!ready) {
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="flex h-14 items-center justify-between border-b border-border bg-surface px-4">
        <div className="font-semibold">Teacher AI Exam Tool</div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted">{user?.full_name}</span>
          <button className="btn-secondary" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <aside className="w-56 border-r border-border bg-surface p-3">
          <nav className="space-y-1">
            {NAV.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={`block rounded-md px-3 py-2 text-sm ${pathname === n.href ? "bg-primary text-white" : "text-text hover:bg-surface2"}`}
              >
                {n.label}
              </Link>
            ))}
          </nav>
        </aside>
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
