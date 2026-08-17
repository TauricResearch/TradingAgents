"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, setSession } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("admin@local");
  const [password, setPassword] = useState("admin123");
  const [name, setName] = useState("Local Admin");
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res =
        mode === "login" ? await api.login(email, password) : await api.register(email, password, name);
      setSession(res.access_token, res.user);
      router.push("/");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-6">
      <p className="text-xs tracking-[0.28em] text-gold">INDIAN EQUITIES RESEARCH TERMINAL</p>
      <h1 className="mt-3 text-3xl font-semibold">TradingAgents</h1>
      <p className="mt-2 text-sm text-mist">
        Multi-agent research for NSE/BSE names. This is a decision aid, not a broker and not a profit guarantee.
      </p>
      <form onSubmit={submit} className="mt-8 space-y-3 rounded-xl border border-line bg-ink-800 p-5">
        {mode === "register" && (
          <input className="w-full rounded-md border border-line bg-ink-900 px-3 py-2" value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" />
        )}
        <input className="w-full rounded-md border border-line bg-ink-900 px-3 py-2" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" />
        <input className="w-full rounded-md border border-line bg-ink-900 px-3 py-2" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" />
        {error && <p className="text-sm text-loss">{error}</p>}
        <button className="w-full rounded-md bg-gold py-2 text-sm font-semibold text-ink-950">
          {mode === "login" ? "Enter terminal" : "Create local account"}
        </button>
        <button type="button" className="w-full text-sm text-mist" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Need an account?" : "Have an account?"}
        </button>
      </form>
      <p className="mt-4 text-xs text-mist">
        Engine: {health.data?.status === "ok" ? "online" : health.isError ? "backend unreachable" : "checking…"}
        . Local default login is admin@local / admin123 until you change it.
      </p>
    </div>
  );
}
