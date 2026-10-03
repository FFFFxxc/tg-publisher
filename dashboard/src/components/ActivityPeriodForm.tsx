"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { INPUT } from "@/components/ui";

export default function ActivityPeriodForm({ initialMinutes }: { initialMinutes: number }) {
  const [minutes, setMinutes] = useState(String(initialMinutes));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const router = useRouter();

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setMessage(""); setError("");
    try {
      const response = await fetch("/api/dash/activity-settings", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ interval_minutes: Number(minutes) }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.error || `ошибка ${response.status}`);
      setMinutes(String(data.interval_minutes));
      setMessage(`Сохранено: одна реакция раз в ${data.interval_minutes} мин.`);
      router.refresh();
    } catch (e: any) {
      setError(e?.message ?? "Не удалось сохранить период");
    } finally { setBusy(false); }
  }

  return <form onSubmit={save} className="grid gap-3 sm:grid-cols-[minmax(220px,320px)_auto]">
    <label className="field-label">Период между реакциями, минут
      <input type="number" min={1} max={1440} step={1} value={minutes}
        onChange={(e) => setMinutes(e.target.value)} className={`w-full ${INPUT}`} />
    </label>
    <div className="flex items-end"><button disabled={busy} className="button-primary disabled:opacity-50">
      {busy ? "Сохранение…" : "Сохранить период"}
    </button></div>
    <span className="field-help sm:col-span-2">Каждый включённый аккаунт ставит максимум одну новую реакцию за период. Значение применяется сразу, без перезапуска.</span>
    {(message || error) && <div role="status" className={`sm:col-span-2 text-xs ${error ? "text-red-300" : "text-emerald-300"}`}>{error || message}</div>}
  </form>;
}
