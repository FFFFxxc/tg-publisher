"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Props = {
  path: string;
  label: string;
  method?: string;
  body?: unknown;
  confirm?: string;
  variant?: "default" | "danger" | "primary";
  doneLabel?: string;
};

const VARIANTS = {
  default: "border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-zinc-200",
  primary: "border-sky-700 bg-sky-800 hover:bg-sky-700 text-sky-100",
  danger: "border-red-800 bg-red-900/70 hover:bg-red-800 text-red-200",
};

async function pollAction(id: string): Promise<any> {
  for (let i = 0; i < 150; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    try {
      const res = await fetch(`/api/dash/actions/${id}`);
      if (res.ok) {
        const a = await res.json();
        if (a.status === "completed" || a.status === "failed") return a;
      }
    } catch {
      // сеть мигнула — продолжаем опрос
    }
  }
  return { status: "failed", error: "истекло время ожидания действия" };
}

function summarize(r: any): string {
  if (!r || typeof r !== "object") return "";
  if (typeof r.status === "string") return r.status;
  if (r.added !== undefined) return `+${r.added}`;
  if (r.posts !== undefined) return `${r.posts} постов`;
  if (typeof r.reply === "string" && r.reply) return r.reply.slice(0, 80);
  return "";
}

/**
 * Кнопка действия: создаёт persistent action на Control API и дожидается
 * реального backend-статуса (pending -> completed/failed), никакого «оптимистично готово».
 */
export default function ActionButton({
  path,
  label,
  method = "POST",
  body,
  confirm,
  variant = "default",
  doneLabel = "Готово",
}: Props) {
  const [state, setState] = useState<"idle" | "run" | "ok" | "err">("idle");
  const [msg, setMsg] = useState("");
  const router = useRouter();

  async function run() {
    if (state === "run") return;
    if (confirm && !window.confirm(confirm)) return;
    setState("run");
    setMsg("");
    try {
      const res = await fetch(`/api/dash/${path}`, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.error || `ошибка ${res.status}`);
      if (data?.action_id) {
        const done = await pollAction(data.action_id);
        if (done.status === "completed") {
          setState("ok");
          setMsg(`${doneLabel}${summarize(done.result) ? `: ${summarize(done.result)}` : ""}`);
        } else {
          setState("err");
          setMsg(done.error || "действие не удалось");
        }
      } else {
        setState("ok");
        setMsg(doneLabel);
      }
      router.refresh();
    } catch (e: any) {
      setState("err");
      setMsg(e?.message ?? "ошибка");
    }
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <button
        onClick={run}
        disabled={state === "run"}
        className={`rounded border px-2 py-1 text-xs disabled:opacity-50 ${VARIANTS[variant]}`}
      >
        {state === "run" ? "…" : label}
      </button>
      {msg && (
        <span className={`text-xs ${state === "err" ? "text-red-400" : "text-emerald-400"}`}>{msg}</span>
      )}
    </span>
  );
}
