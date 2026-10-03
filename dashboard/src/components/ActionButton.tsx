"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { humanLabel } from "@/components/ui";

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
  default: "button-secondary",
  primary: "button-primary",
  danger: "button-danger",
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
  if (typeof r.status === "string") return r.status === "already_published" ? "Уже опубликован" : humanLabel(r.status);
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
          if (["failed", "ambiguous", "pending", "skipped"].includes(done.result?.status)) {
            throw new Error(`Публикация не завершена: ${humanLabel(done.result.status)}. Подробности — в карточке поста.`);
          }
          if (done.result?.ai_status && !["generated", "manual"].includes(done.result.ai_status)) {
            throw new Error(`Текст не создан: ${humanLabel(done.result.ai_status)}. Подробности — в истории.`);
          }
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
        className={`${VARIANTS[variant]} disabled:cursor-not-allowed disabled:opacity-50`}
      >
        {state === "run" ? "Выполняется…" : label}
      </button>
      {msg && (
        <span role="status" className={`max-w-xs text-xs ${state === "err" ? "text-red-300" : "text-emerald-300"}`}>{msg}</span>
      )}
    </span>
  );
}
