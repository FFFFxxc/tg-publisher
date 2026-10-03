"use client";

import { useEffect, useState } from "react";
import ActionButton from "@/components/ActionButton";
import { Badge, Card, Dot, Stat } from "@/components/ui";
import { fmtDate } from "@/lib/format";

const STATUSES = ["candidate", "pending", "processing", "published", "failed", "ambiguous", "skipped", "expired"];

export default function Overview({ initial }: { initial: any }) {
  const [d, setD] = useState<any>(initial);
  const [err, setErr] = useState("");

  useEffect(() => {
    const t = setInterval(async () => {
      try {
        const r = await fetch("/api/dash/overview");
        if (r.ok) {
          setD(await r.json());
          setErr("");
        } else {
          setErr(`Control API ${r.status}`);
        }
      } catch {
        setErr("нет связи");
      }
    }, 15000);
    return () => clearInterval(t);
  }, []);

  if (!d) return null;
  const w = d.worker ?? {};
  const q = d.queue ?? {};
  const sched = d.schedule ?? {};

  return (
    <div className="space-y-4">
      {err && (
        <div className="rounded border border-amber-800 bg-amber-950/40 p-2 text-xs text-amber-300">
          автообновление: {err}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Worker"
          value={
            <span className="flex items-center gap-2">
              <Dot ok={!!w.online} />
              {w.online ? "online" : "offline"}
            </span>
          }
          hint={`v${w.version ?? "?"}`}
        />
        <Stat
          label="Telegram"
          value={
            <span className="flex items-center gap-2">
              <Dot ok={!!w.telegram_connected} />
              {w.telegram_connected ? "connected" : "disconnected"}
            </span>
          }
          hint={`transport: ${w.transport ?? "?"}`}
        />
        <Stat
          label="БД"
          value={
            <span className="flex items-center gap-2">
              <Dot ok={!!d.db?.ok} />
              {d.db?.ok ? "ok" : "fail"}
            </span>
          }
          hint={d.db?.schema ? `schema: ${d.db.schema}` : undefined}
        />
        <Stat label="Канал" value={d.destination ?? "—"} hint={`источников включено: ${d.sources_enabled ?? 0}`} />
        <Stat label="Опубликовано сегодня" value={d.published?.today ?? 0} />
        <Stat label="Опубликовано за 24ч" value={d.published?.h24 ?? 0} />
        <Stat
          label="Последний collect"
          value={d.last_collect_age_s != null ? `${d.last_collect_age_s} с назад` : "—"}
        />
        <Stat label="Последняя публикация" value={fmtDate(d.last_published_at)} />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Очередь по статусам">
          <div className="flex flex-wrap gap-x-3 gap-y-2">
            {STATUSES.map((s) => (
              <span key={s} className="flex items-center gap-1">
                <Badge v={s} />
                <span className="text-sm text-zinc-300">{q[s] ?? 0}</span>
              </span>
            ))}
          </div>
        </Card>

        <Card
          title="Расписание"
          right={
            <ActionButton
              path="schedule"
              method="PUT"
              body={{ publishing_paused: !sched.paused }}
              label={sched.paused ? "Возобновить" : "Пауза"}
              variant={sched.paused ? "primary" : "danger"}
              doneLabel={sched.paused ? "публикация возобновлена" : "публикация на паузе"}
            />
          }
        >
          <div className="space-y-1 text-sm text-zinc-300">
            <div>
              Следующий слот: <b>{sched.next_slot ? fmtDate(sched.next_slot) : "—"}</b>
            </div>
            <div className="flex items-center gap-1.5">
              Следующий тип: {sched.next_kind ? <Badge v={sched.next_kind} /> : "—"}
            </div>
            <div className="text-zinc-400">
              {(sched.publish_times ?? []).join(", ") || "интервал"} · [{(sched.pattern ?? []).join(",")}] ·{" "}
              {sched.tz}
            </div>
            {sched.paused && <div className="text-red-400">Публикация на паузе (collector продолжает работать)</div>}
          </div>
        </Card>

        <Card title="Последняя ошибка">
          {d.last_error ? (
            <div className="text-sm text-zinc-300">
              <Badge v={d.last_error.level} /> <Badge v={d.last_error.type} />{" "}
              <span className="text-xs text-zinc-500">{fmtDate(d.last_error.created_at)}</span>
              <div className="mt-1 break-words text-zinc-400">{d.last_error.message}</div>
            </div>
          ) : (
            <div className="text-sm text-zinc-500">пока пусто</div>
          )}
        </Card>

        <Card title="Heartbeats">
          <div className="space-y-1 text-sm text-zinc-300">
            {Object.entries(d.worker?.heartbeat_age_s ?? {}).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span>{k}</span>
                <span className="text-zinc-500">{String(v)} с назад</span>
              </div>
            ))}
            {Object.keys(d.worker?.heartbeat_age_s ?? {}).length === 0 && (
              <span className="text-zinc-500">нет данных</span>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
