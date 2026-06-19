"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { bootstrapAuth, getAccessToken } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    (async () => {
      await bootstrapAuth();
      const t = getAccessToken();
      if (t) router.replace("/dashboard");
      else router.replace("/login");
    })();
  }, [router]);
  return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
}
