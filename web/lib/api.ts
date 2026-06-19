"use client";
import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

let accessToken: string | null = null;
let currentUser: any = null;
const listeners = new Set<() => void>();

export function setAccessToken(t: string | null) {
  accessToken = t;
  listeners.forEach((l) => l());
}

export function getAccessToken() {
  return accessToken;
}

export function setCurrentUser(u: any) {
  currentUser = u;
  listeners.forEach((l) => l());
}

export function getCurrentUser() {
  return currentUser;
}

export function useAuth() {
  const [, force] = useState(0);
  useEffect(() => {
    const l = () => force((n) => n + 1);
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, []);
  return { accessToken, currentUser };
}

export class ProblemError extends Error {
  code: string;
  status: number;
  errors: any[];
  request_id?: string;
  constructor(status: number, body: any) {
    super(body.detail || body.title || "Error");
    this.status = status;
    this.code = body.code || "INTERNAL";
    this.errors = body.errors || [];
    this.request_id = body.request_id;
  }
}

async function refresh(): Promise<string | null> {
  const r = await fetch(`${API_BASE}/api/v1/auth/refresh`, { method: "POST", credentials: "include" });
  if (!r.ok) return null;
  const data = await r.json();
  setAccessToken(data.access_token);
  return data.access_token;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let res = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: "include" });
  if (res.status === 401) {
    const t = await refresh();
    if (t) {
      headers.Authorization = `Bearer ${t}`;
      res = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: "include" });
    } else {
      setAccessToken(null);
      setCurrentUser(null);
    }
  }
  if (!res.ok) {
    let body: any = {};
    try {
      body = await res.json();
    } catch {
      body = { detail: res.statusText };
    }
    throw new ProblemError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function bootstrapAuth() {
  // If we have a refresh cookie, get a new access token.
  if (!accessToken) {
    const t = await refresh();
    if (t) {
      // fetch /me
      try {
        const me = await apiFetch<any>("/api/v1/me");
        setCurrentUser(me);
      } catch {
        setCurrentUser(null);
      }
    }
  }
  return accessToken;
}
