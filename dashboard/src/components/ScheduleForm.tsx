"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, INPUT } from "@/components/ui";
import { fmtDate } from "@/lib/format";

const FIELDS: [string, string][] = [
  ["candidate_min_age_min", "мин. возраст кандидата, мин"],
  ["max_post_age_hours", "макс. возраст поста, ч"],
  ["best_min_score", "мин. score для публикации"],
  ["baseline_days", "базлайн источника, дней"],
  ["own_min_age_days", "мин. возраст своего поста, дней"],
  ["repost_cooldown_days", "кулдаун репоста, дней"],
  ["collect_interval", "интервал collect, сек"],
];

export default function ScheduleForm({ initial }: { initial: any }) {
  const s = initial?.settings ?? {};
  const [tz, setTz] = useState(s.tz_name ?? "Europe/Moscow");
  const [times, setTimes] = useState((s.publish_times ?? []).join(", "));
  const [pattern, setPattern] = useState((s.schedule_pattern ?? []).join(","));
  const [nums, setNums] = useState<Record<string, number>>({
    candidate_min_age_min: s.candidate_min_age_min ?? 120,
    max_post_age_hours: s.max_post_age_hours ?? 48,
    best_min_score: s.best_min_score ?? 1,
    baseline_days: s.baseline_days ?? 7,
    own_min_age_days: s.own_min_age_days ?? 14,
    repost_cooldown_days: s.repost_cooldown_days ?? 60,
    collect_interval: s.collect_interval ?? 300,
  });
  const [paused, setPaused] = useState(!!s.publishing_paused);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg("");
    setErr("");
    try {
      const res = await fetch("/api/dash/schedule", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tz_name: tz,
          publish_times: times.split(",").map((x: string) => x.trim()).filter(Boolean),
          schedule_pattern: pattern.split(",").map((x: string) => x.trim()).filter(Boolean),
          ...nums,
          publishing_paused: paused,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.error || `ошибка ${res.status}`);
      setMsg("сохранено — рестарт не нужен, воркер подхватит настройки сам");
      router.refresh();
    } catch (e: any) {
      setErr(e?.message ?? "ошибка");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card title="Текущий слот (обновится после сохранения страницы)">
        <div className="text-sm text-zinc-300">
          <div>
            Следующий слот: <b>{initial?.next_slot ? fmtDate(initial.next_slot) : "—"}</b>
          </div>
          <div>Следующий тип: {initial?.next_kind ?? "—"}</div>
          <div>Индекс в паттерне: {initial?.pattern_index ?? 0}</div>
        </div>
      </Card>

      <Card title="Настройки (ENV — бутстрап, эти значения живут в БД)">
        <form onSubmit={save} className="grid gap-3 md:grid-cols-2">
          <label className="text-xs text-zinc-500">
            Таймзона
            <input value={tz} onChange={(e) => setTz(e.target.value)} className={`w-full ${INPUT}`} />
          </label>
          <label className="text-xs text-zinc-500">
            Время публикаций (HH:MM через запятую)
            <input value={times} onChange={(e) => setTimes(e.target.value)} className={`w-full ${INPUT}`} />
          </label>
          <label className="text-xs text-zinc-500">
            Паттерн (parsed/old через запятую)
            <input value={pattern} onChange={(e) => setPattern(e.target.value)} className={`w-full ${INPUT}`} />
          </label>
          <label className="flex items-center gap-2 pt-5 text-sm text-zinc-300">
            <input type="checkbox" checked={paused} onChange={(e) => setPaused(e.target.checked)} />
            Пауза публикации (collector продолжает работать)
          </label>
          {FIELDS.map(([k, label]) => (
            <label key={k} className="text-xs text-zinc-500">
              {label}
              <input
                type="number"
                step="any"
                value={nums[k]}
                onChange={(e) => setNums({ ...nums, [k]: Number(e.target.value) })}
                className={`w-full ${INPUT}`}
              />
            </label>
          ))}
          <div className="flex items-center gap-3 md:col-span-2">
            <button
              disabled={busy}
              className="rounded border border-sky-700 bg-sky-800 px-3 py-1.5 text-sm hover:bg-sky-700 disabled:opacity-50"
            >
              {busy ? "сохранение…" : "Сохранить"}
            </button>
            {msg && <span className="text-xs text-emerald-400">{msg}</span>}
            {err && <span className="text-xs text-red-400">{err}</span>}
          </div>
        </form>
      </Card>
    </div>
  );
}
