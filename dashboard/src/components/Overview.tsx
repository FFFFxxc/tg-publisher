"use client";

import { useEffect, useMemo, useState } from "react";
import ActionButton from "@/components/ActionButton";
import MediaPreview from "@/components/MediaPreview";
import { Card, Dot, Notice, Stat, humanLabel } from "@/components/ui";
import { cleanPostText, excerpt, fmtAge, fmtDate } from "@/lib/format";

const PROCESS_COLORS: Record<string, string> = {
  green: "bg-emerald-400 shadow-[0_0_0_4px_rgba(52,211,153,.1)]",
  yellow: "bg-amber-400 shadow-[0_0_0_4px_rgba(251,191,36,.1)]",
  red: "bg-red-400 shadow-[0_0_0_4px_rgba(248,113,113,.1)]",
};

function ProcessDot({ state }: { state: string }) {
  return <span aria-label={state === "green" ? "работает вовремя" : state === "yellow" ? "есть задержка" : "процесс завис"} className={`inline-block h-2.5 w-2.5 rounded-full ${PROCESS_COLORS[state] ?? PROCESS_COLORS.red}`} />;
}

function Destination({ value, sources }: { value: any; sources: number }) {
  const d = typeof value === "string" ? { ref: value, title: value } : value ?? {};
  return (
    <div className="surface bg-gradient-to-br from-slate-800/70 to-slate-900/40 p-4">
      <div className="text-[11px] font-semibold uppercase tracking-[.08em] text-slate-500">Канал назначения</div>
      <div className="mt-2 flex items-center gap-3">
        {d.avatar_url ? <img src={d.avatar_url} alt="" className="h-11 w-11 rounded-full border border-slate-700 object-cover" /> :
          <div className="grid h-11 w-11 place-items-center rounded-full bg-sky-950 text-sky-300" aria-hidden="true">
            <svg viewBox="0 0 24 24" className="h-6 w-6 fill-current"><path d="M21.6 3.3 18.4 20c-.2 1.2-.9 1.5-1.9.9l-4.9-3.6-2.4 2.3c-.3.3-.5.5-1 .5l.4-5 9-8.1c.4-.4-.1-.6-.6-.2L5.8 13.9 1 12.4c-1-.3-1-1 .2-1.5L20 3.7c.9-.3 1.7.2 1.6-.4Z" /></svg>
          </div>}
        <div className="min-w-0"><div className="truncate text-lg font-semibold text-slate-50">{d.title || "—"}</div><div className="truncate text-xs text-slate-500">{d.ref || ""}</div></div>
      </div>
      <div className="mt-2 text-xs text-slate-400">Активных источников: {sources}</div>
    </div>
  );
}

function Funnel({ funnel }: { funnel: any }) {
  const items = [
    ["Найдено", Number(funnel?.found || 0), "bg-sky-500"],
    ["Готово", Number(funnel?.ready || 0), "bg-amber-400"],
    ["Опубликовано", Number(funnel?.published || 0), "bg-emerald-400"],
  ].filter((x) => Number(x[1]) > 0) as [string, number, string][];
  const max = Math.max(...items.map((x) => x[1]), 1);
  return items.length ? <div className="space-y-3">{items.map(([label, n, color]) =>
    <div key={label}><div className="mb-1 flex justify-between text-xs"><span className="text-slate-300">{label}</span><b>{n}</b></div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-800"><div className={`h-full rounded-full ${color}`} style={{ width: `${Math.max(6, n / max * 100)}%` }} /></div>
    </div>)}</div> : <div className="text-sm text-slate-400">Очередь пока пуста.</div>;
}

function WeekChart({ data }: { data: any[] }) {
  const max = Math.max(1, ...data.flatMap((x) => [Number(x.published || 0), Number(x.reactions || 0)]));
  const points = (key: string) => data.map((x, i) => `${12 + i * 46},${102 - Number(x[key] || 0) / max * 82}`).join(" ");
  return <div>
    <div className="mb-3 flex gap-4 text-xs text-slate-400"><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-sky-400" />Обычные публикации</span><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-fuchsia-400" />Реакции аккаунтов</span></div>
    <svg viewBox="0 0 300 128" className="h-48 w-full" role="img" aria-label="Публикации и реакции за 7 дней">
      {[20, 61, 102].map(y => <line key={y} x1="10" x2="290" y1={y} y2={y} stroke="rgb(51 65 85)" strokeWidth="1" />)}
      <polyline points={points("published")} fill="none" stroke="rgb(56 189 248)" strokeWidth="3" strokeLinejoin="round" />
      <polyline points={points("reactions")} fill="none" stroke="rgb(232 121 249)" strokeWidth="3" strokeLinejoin="round" />
      {data.map((x, i) => <text key={x.date} x={12 + i * 46} y="122" textAnchor="middle" fill="rgb(148 163 184)" fontSize="9">{String(x.date).slice(5).replace("-", ".")}</text>)}
    </svg>
    <p className="text-xs text-slate-500">Реакции — фактические отметки, поставленные подключёнными аккаунтами в эти дни.</p>
  </div>;
}

export default function Overview({ initial }: { initial: any }) {
  const [d, setD] = useState<any>(initial);
  const [err, setErr] = useState("");
  const [replacing, setReplacing] = useState(false);

  useEffect(() => {
    const t = setInterval(async () => {
      try {
        const r = await fetch("/api/dash/overview");
        if (r.ok) { setD(await r.json()); setErr(""); } else setErr(`Control API ${r.status}`);
      } catch { setErr("нет связи"); }
    }, 15000);
    return () => clearInterval(t);
  }, []);

  async function replaceNext() {
    const p = d.next_post;
    if (!p || p.selection === "scheduled") return;
    setReplacing(true);
    try {
      const r = await fetch("/api/dash/overview/next-post/replace", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: p.kind, current: p.kind === "old" ? p.group_key : p.id }),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(body.error || `ошибка ${r.status}`);
      setD((old: any) => ({ ...old, next_post: body.next_post }));
      setErr("");
    } catch (e: any) { setErr(e?.message || "не удалось заменить публикацию"); }
    finally { setReplacing(false); }
  }

  const w = d?.worker ?? {}, sched = d?.schedule ?? {}, next = d?.next_post;
  const postText = useMemo(() => cleanPostText(next?.text, next?.source_ref), [next]);

  if (!d) return null;
  return <div className="space-y-4">
    {err && <Notice tone="warning">Не удалось обновить данные: {err}. Показаны последние полученные значения.</Notice>}

    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Stat label="Бот" value={<span className="flex items-center gap-2"><Dot ok={!!w.online} />{w.online ? "Работает" : "Не отвечает"}</span>} hint={`Версия ${w.version ?? "не определена"}`} tone={w.online ? "good" : "warn"} />
      <Stat label="Telegram" value={<span className="flex items-center gap-2"><Dot ok={!!w.telegram_connected} />{w.telegram_connected ? "Подключён" : "Нет связи"}</span>} hint={`Подключение: ${w.transport ?? "не определено"}`} tone={w.telegram_connected ? "good" : "warn"} />
      <Stat label="Опубликовано сегодня" value={d.published?.today ?? 0} hint={`За 24 часа: ${d.published?.h24 ?? 0}`} />
      <Destination value={d.destination} sources={d.sources_enabled ?? 0} />
    </div>

    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Ближайшая публикация" description="Реальный следующий материал с учётом ручного расписания и рейтинга."
        right={<div className="flex flex-wrap gap-2">
          {next && ["ranking", "override"].includes(next.selection) && <button className="button-secondary" disabled={replacing} onClick={replaceNext}>{replacing ? "Подбираем…" : "Заменить"}</button>}
          <ActionButton path="schedule" method="PUT" body={{ publishing_paused: !sched.paused }} label={sched.paused ? "Возобновить" : "Приостановить"} variant={sched.paused ? "primary" : "default"} doneLabel={sched.paused ? "публикация возобновлена" : "публикация на паузе"} />
        </div>}>
        {next ? <div className="grid gap-4 sm:grid-cols-[160px_1fr]">
          <MediaPreview postId={next.id ?? next.group_key} thumbnail src={next.preview_url} />
          <div className="min-w-0 space-y-2 text-sm text-slate-300">
            <div className="flex flex-wrap items-center gap-2"><b title={next.kind === "old" ? "Архив ранжируется по количеству реакций" : "Итоговый рейтинг относительно средних просмотров и вовлечённости этого источника"} className="text-lg text-sky-300">{next.kind === "old" ? "Реакции" : "Score"} {next.score != null ? Number(next.score).toFixed(next.kind === "old" ? 0 : 2) : "—"}</b><span className="text-xs text-slate-500">{humanLabel(next.media_type)}</span></div>
            <p className="line-clamp-4 text-slate-300">{excerpt(postText, 260) || "Публикация без подписи"}</p>
            <div className="text-xs text-slate-500">{next.source_title || next.source_ref || "Архив канала"} · {next.scheduled_at ? `назначено на ${fmtDate(next.scheduled_at)}` : `следующий слот ${fmtDate(sched.next_slot)}`}</div>
            <a href={next.post_url} className="text-xs text-sky-400 hover:text-sky-300">Открыть публикацию →</a>
          </div>
        </div> : <div className="text-sm text-slate-400">Подходящего материала пока нет.</div>}
        {sched.paused && <div className="mt-3 text-sm text-amber-300">Автопубликация приостановлена. Источники продолжают обновляться.</div>}
      </Card>

      <Card title="Очередь публикаций" description="Найдено → готово к публикации → опубликовано. Нулевые этапы скрыты.">
        <Funnel funnel={d.queue_funnel} />
      </Card>

      <Card title="Активность процессов" description="Зелёный — вовремя, жёлтый — задержка, красный — процесс мог зависнуть.">
        <div className="space-y-3">{(w.processes ?? []).map((p: any) =>
          <div key={p.id} className="flex items-center justify-between gap-4 text-sm"><span className="flex items-center gap-2"><ProcessDot state={p.state} />{p.label}</span><span className={p.state === "red" ? "text-red-300" : p.state === "yellow" ? "text-amber-300" : "text-slate-400"}>{fmtAge(p.age_s)}</span></div>)}
          {!(w.processes ?? []).length && <span className="text-sm text-slate-400">Пока нет данных.</span>}
        </div>
      </Card>

      <Card title="Последняя проблема" description="Последнее предупреждение с переходом к связанному посту.">
        {d.last_error ? <div className="space-y-3 text-sm">
          <div><span className={d.last_error.level === "error" ? "text-red-300" : "text-amber-300"}>{humanLabel(d.last_error.type)}</span><span className="ml-2 text-xs text-slate-500">{fmtDate(d.last_error.created_at)}</span></div>
          <p className="break-words text-slate-300">{d.last_error.message || "Подробности ошибки не записаны"}</p>
          <div className="flex flex-wrap gap-2">{d.last_error.post_url && <a href={d.last_error.post_url} className="button-secondary">Открыть пост</a>}
            {d.last_error.retryable && <ActionButton path={d.last_error.retry_path} body={d.last_error.retry_body ?? undefined} label="Повторить" doneLabel="повтор поставлен в очередь" />}</div>
        </div> : <div className="text-sm text-slate-400">Проблем не зафиксировано.</div>}
      </Card>
    </div>

    <Card title="Публикации и реакции за 7 дней" description="Фактическая история работы канала по дням.">
      <WeekChart data={d.chart_7d ?? []} />
    </Card>
  </div>;
}
