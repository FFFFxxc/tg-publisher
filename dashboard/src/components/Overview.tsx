"use client";

import { useEffect, useState } from "react";
import ActionButton from "@/components/ActionButton";
import { Badge, Card, Dot, Notice, Stat, humanLabel } from "@/components/ui";
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
        <Notice tone="warning">Не удалось обновить данные автоматически: {err}. На экране остаются последние полученные значения.</Notice>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Бот"
          value={
            <span className="flex items-center gap-2">
              <Dot ok={!!w.online} />
              {w.online ? "Работает" : "Не отвечает"}
            </span>
          }
          hint={`Версия ${w.version ?? "не определена"}`}
          tone={w.online ? "good" : "warn"}
        />
        <Stat
          label="Telegram"
          value={
            <span className="flex items-center gap-2">
              <Dot ok={!!w.telegram_connected} />
              {w.telegram_connected ? "Подключён" : "Нет связи"}
            </span>
          }
          hint={`Способ подключения: ${w.transport ?? "не определён"}`}
          tone={w.telegram_connected ? "good" : "warn"}
        />
        <Stat
          label="Хранилище данных"
          value={
            <span className="flex items-center gap-2">
              <Dot ok={!!d.db?.ok} />
              {d.db?.ok ? "Доступно" : "Ошибка"}
            </span>
          }
          hint={d.db?.schema ? `Раздел: ${d.db.schema}` : undefined}
          tone={d.db?.ok ? "good" : "warn"}
        />
        <Stat label="Канал назначения" value={d.destination ?? "—"} hint={`Активных источников: ${d.sources_enabled ?? 0}`} />
        <Stat label="Опубликовано сегодня" value={d.published?.today ?? 0} />
        <Stat label="Опубликовано за 24 часа" value={d.published?.h24 ?? 0} />
        <Stat
          label="Последняя проверка источников"
          value={d.last_collect_age_s != null ? `${d.last_collect_age_s} с назад` : "—"}
        />
        <Stat label="Последняя публикация" value={fmtDate(d.last_published_at)} />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Очередь публикаций" description="Сколько материалов находится на каждом этапе.">
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
          title="Ближайшая публикация"
          description="План работает по московскому или выбранному в настройках времени."
          right={
            <ActionButton
              path="schedule"
              method="PUT"
              body={{ publishing_paused: !sched.paused }}
              label={sched.paused ? "Возобновить публикации" : "Приостановить"}
              variant={sched.paused ? "primary" : "danger"}
              doneLabel={sched.paused ? "публикация возобновлена" : "публикация на паузе"}
            />
          }
        >
          <div className="space-y-1 text-sm text-zinc-300">
            <div>
              Следующая публикация: <b>{sched.next_slot ? fmtDate(sched.next_slot) : "—"}</b>
            </div>
            <div className="flex items-center gap-1.5">
              Тип материала: {sched.next_kind ? <Badge v={sched.next_kind} /> : "—"}
            </div>
            <div className="text-zinc-400">
              Время: {(sched.publish_times ?? []).join(", ") || "по интервалу"} · Часовой пояс: {sched.tz}
            </div>
            {sched.paused && <div className="text-amber-300">Автопубликация приостановлена. Источники продолжают обновляться.</div>}
          </div>
        </Card>

        <Card title="Последняя проблема" description="Самое свежее предупреждение или ошибка в работе бота.">
          {d.last_error ? (
            <div className="text-sm text-zinc-300">
              <Badge v={d.last_error.level} /> <span className="text-xs text-slate-400">{humanLabel(d.last_error.type)}</span>{" "}
              <span className="text-xs text-zinc-500">{fmtDate(d.last_error.created_at)}</span>
              <div className="mt-1 break-words text-zinc-400">{d.last_error.message}</div>
            </div>
          ) : (
            <div className="text-sm text-slate-400">Проблем не зафиксировано.</div>
          )}
        </Card>

        <Card title="Активность процессов" description="Сколько секунд прошло с последнего сигнала каждого процесса.">
          <div className="space-y-1 text-sm text-zinc-300">
            {Object.entries(d.worker?.heartbeat_age_s ?? {}).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span>{k === "worker" ? "Основной процесс" : k === "collector" ? "Проверка источников" : k === "publisher" ? "Публикация" : humanLabel(k)}</span>
                <span className="text-zinc-500">{String(v)} с назад</span>
              </div>
            ))}
            {Object.keys(d.worker?.heartbeat_age_s ?? {}).length === 0 && (
              <span className="text-slate-400">Пока нет данных.</span>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
