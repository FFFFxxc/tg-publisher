"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import ActionButton from "@/components/ActionButton";
import MediaPreview from "@/components/MediaPreview";
import PublisherIcon from "@/components/PublisherIcon";
import type { PublisherIconName } from "@/components/PublisherIcon";
import { humanLabel } from "@/components/ui";
import { cleanPostText, excerpt, fmtAge, fmtDate } from "@/lib/format";
import { nativeScheduleNotice } from "@/lib/nativeSchedule";
import { homeSlot } from "@/lib/homeOverview";

function Heading({ icon, children }: { icon: PublisherIconName; children: ReactNode }) {
  return <h2 className="home-heading"><PublisherIcon name={icon} />{children}</h2>;
}

function Dot({ state }: { state: "green" | "yellow" | "red" | "unknown" }) {
  const label = { green: "Работает вовремя", yellow: "Есть задержка", red: "Нет связи или обновлений", unknown: "Нет данных" }[state];
  return <span className="home-dot" data-state={state} role="img" aria-label={label} title={label} />;
}

function Metric({ icon, label, children, hint }: { icon: PublisherIconName; label: string; children: ReactNode; hint: string }) {
  return <section className="home-card home-metric">
    <h2><span className="home-icon-tile"><PublisherIcon name={icon} /></span>{label}</h2>
    <div className="home-metric-value">{children}</div>
    <p>{hint}</p>
  </section>;
}

function Funnel({ funnel }: { funnel: any }) {
  const items = [
    { label: "Найдено", n: Number(funnel?.found || 0), color: "purple" },
    { label: "Готово к публикации", n: Number(funnel?.ready || 0), color: "blue" },
    { label: "Опубликовано", n: Number(funnel?.published || 0), color: "green" },
  ];
  const max = Math.max(1, ...items.map(x => x.n));
  return items.some(x => x.n > 0) ? <div className="home-funnel">{items.map(({label, n, color}) =>
    <div key={label} data-color={color}>
      <div className="home-funnel-label"><span>{label}</span><b>{n}</b></div>
      <div className="home-bar" aria-hidden="true"><span style={{ width: `${n / max * 100}%` }} /></div>
    </div>)}</div> : <p className="home-muted">Очередь пока пуста.</p>;
}

function WeekChart({ data }: { data: any[] }) {
  const max = Math.max(1, ...data.flatMap((x) => [Number(x.published || 0), Number(x.reactions || 0)]));
  const points = (key: string) => data.map((x, i) => `${12 + i * 46},${102 - Number(x[key] || 0) / max * 82}`).join(" ");
  return <section className="home-card home-week">
    <Heading icon="pulse">Публикации и реакции за 7 дней</Heading>
    <div className="home-week-legend"><span>Обычные публикации</span><span>Реакции аккаунтов</span></div>
    <svg viewBox="0 0 300 128" role="img" aria-label="Публикации и реакции за 7 дней">
      {[20, 61, 102].map(y => <line key={y} x1="10" x2="290" y1={y} y2={y} stroke="var(--home-line)" strokeWidth="1" />)}
      <polyline points={points("published")} fill="none" stroke="var(--home-accent)" strokeWidth="2" strokeLinejoin="round" />
      <polyline points={points("reactions")} fill="none" stroke="var(--home-green)" strokeWidth="2" strokeLinejoin="round" />
      {data.map((x, i) => <text key={x.date} x={12 + i * 46} y="122" textAnchor="middle" fill="var(--home-muted)" fontSize="8">{String(x.date).slice(5).replace("-", ".")}</text>)}
    </svg>
    <p className="home-muted">Реакции — фактические отметки подключённых аккаунтов.</p>
  </section>;
}

export default function Overview({ initial }: { initial: any }) {
  const [d, setD] = useState<any>(initial);
  const [err, setErr] = useState("");
  const [replacing, setReplacing] = useState(false);

  useEffect(() => { setD(initial); }, [initial]);

  useEffect(() => {
    const t = setInterval(async () => {
      try {
        const r = await fetch("/api/dash/overview");
        if (r.ok) {
          const data = await r.json();
          if (data.telegram_schedule?.enabled) {
            try {
              const guard = await fetch("/api/dash/telegram-schedule");
              if (guard.ok) data.telegram_schedule = await guard.json();
            } catch { /* Keep the overview snapshot if only the status refresh fails. */ }
          }
          setD(data); setErr("");
        } else setErr(`Control API ${r.status}`);
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
  const nativeNotice = nativeScheduleNotice(d?.telegram_schedule);
  const slot = next ? homeSlot(next, sched, !!nativeNotice?.waiting) : null;
  const postText = cleanPostText(next?.text, next?.source_ref);
  const destination = typeof d?.destination === "string" ? d.destination : d?.destination?.title || d?.destination?.ref;
  const failure = d?.last_error;

  if (!d) return null;
  return <div className="home-overview">
    {err && <p className="home-update-error" role="alert">Не удалось обновить данные: {err}. Показаны последние полученные значения.</p>}
    {nativeNotice && <section className="home-guard" data-tone={nativeNotice.tone} aria-label="Состояние защиты от сдвоений">
      <span className="home-guard-icon"><PublisherIcon name="shield" /></span>
      <div>
        <h2>{nativeNotice.title}</h2>
        <p>{nativeNotice.detail}</p>
        {nativeNotice.waiting && d.telegram_schedule?.last_scheduled_at && <p>Последний пост в отложке: {fmtDate(d.telegram_schedule.last_scheduled_at)}</p>}
      </div>
      <span className="home-guard-state"><span aria-hidden="true" />{nativeNotice.waiting ? "Ожидание" : "Активна"}</span>
    </section>}

    <div className="home-grid">
      <section className="home-card home-next">
        <div className="home-card-top">
          <Heading icon="clock">Ближайшая публикация</Heading>
          {slot && <span className="home-date home-slot" data-tone={slot.tone}><PublisherIcon name="calendar" />{slot.value}</span>}
        </div>
        {next ? <>
          <div className="home-preview">
            <MediaPreview postId={next.id ?? next.group_key} banner src={next.preview_url} />
            {next.media_type && <span className="home-media-badge"><PublisherIcon name="photo" />{humanLabel(next.media_type)}</span>}
          </div>
          <div className="home-post">
            <span className="home-post-source">{next.source_title || next.source_ref || "Архив канала"}</span>
            <div className="home-post-line">
              <h3>{excerpt(postText, 140) || "Публикация без подписи"}</h3>
              {next.score != null && Number.isFinite(Number(next.score)) && <span className="home-post-score"
                title={next.kind === "old" ? "Число реакций на архивную публикацию" : "Рейтинг относительно средних показателей источника"}>
                {next.kind === "old" ? <PublisherIcon name="heart" /> : null}
                {next.kind === "old" ? `${Number(next.score).toFixed(0)} реакций` : `Рейтинг ${Number(next.score).toFixed(2)}`}
              </span>}
            </div>
            {next.post_url && <a className="home-link" href={next.post_url}>Открыть публикацию <PublisherIcon name="arrow" /></a>}
          </div>
        </> : <p className="home-no-post">Подходящего материала пока нет.</p>}
        <div className="home-actions">
          {next && ["ranking", "override"].includes(next.selection) && <button type="button" className="button-primary home-replace" disabled={replacing} onClick={replaceNext}>
            <PublisherIcon name="swap" />{replacing ? "Подбираем…" : "Заменить"}
          </button>}
          <ActionButton path="schedule" method="PUT" body={{ publishing_paused: !sched.paused }} label={sched.paused ? "Возобновить" : "Приостановить"}
            variant={sched.paused ? "primary" : "default"} doneLabel={sched.paused ? "публикация возобновлена" : "публикация на паузе"} />
        </div>
        {sched.paused && <p className="home-muted">Автопубликация приостановлена. Источники продолжают обновляться.</p>}
      </section>

      <div className="home-summary">
        <div className="home-metrics">
          <Metric icon="bot" label="Бот" hint={`Версия ${w.version ?? "не определена"}`}>
            <Dot state={w.online ? "green" : "red"} />{w.online ? "Работает" : "Не отвечает"}
          </Metric>
          <Metric icon="plane" label="Telegram" hint={`Подключение: ${(w.transport ?? "не определено").toUpperCase()}`}>
            <Dot state={w.telegram_connected ? "green" : "red"} />{w.telegram_connected ? "Подключён" : "Нет связи"}
          </Metric>
          <Metric icon="check" label="Опубликовано сегодня" hint={`${d.published?.h24 ?? 0} за последние 24 часа`}>{d.published?.today ?? 0}</Metric>
          <Metric icon="channel" label="Канал назначения" hint={`Активных источников: ${d.sources_enabled ?? 0}`}>
            <span className="home-destination" title={destination}>{destination || "—"}</span>
          </Metric>
        </div>
        <section className="home-card home-queue">
          <Heading icon="queue">Очередь публикаций</Heading>
          <p className="home-muted">От найденных постов до публикации</p>
          <Funnel funnel={d.queue_funnel} />
        </section>
      </div>

      <section className="home-card home-processes">
        <Heading icon="pulse">Активность процессов</Heading>
        {(w.processes ?? []).length > 0 ? <ul>{w.processes.map((p: any) =>
          <li key={p.id}><span><Dot state={["green", "yellow", "red"].includes(p.state) ? p.state : "unknown"} />{p.label}</span>
            <time data-state={p.state}>{fmtAge(p.age_s)}</time></li>)}</ul> : <p className="home-muted">Пока нет данных.</p>}
      </section>

      <section className="home-card home-failure">
        <Heading icon="warning">Последняя проблема</Heading>
        {failure ? <>
          <div className="home-problem-meta"><span className="home-problem-badge" data-tone={failure.level}>{humanLabel(failure.type)}</span>
            <span>{fmtDate(failure.created_at)}</span></div>
          <p className="home-problem-message">{failure.message || "Подробности ошибки не записаны."}</p>
          <div className="home-actions">
            <a className="home-link" href="/activity">Открыть журнал <PublisherIcon name="arrow" /></a>
            {failure.post_url && <a className="home-link" href={failure.post_url}>Открыть пост <PublisherIcon name="arrow" /></a>}
            {failure.retryable && <ActionButton path={failure.retry_path} body={failure.retry_body ?? undefined} label="Повторить" doneLabel="повтор поставлен в очередь" />}
          </div>
        </> : <p className="home-muted">Проблем не зафиксировано.</p>}
      </section>
    </div>
    <WeekChart data={d.chart_7d ?? []} />
  </div>;
}
