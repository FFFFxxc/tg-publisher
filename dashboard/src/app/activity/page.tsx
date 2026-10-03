import Link from "next/link";
import { pubFetch } from "@/lib/api";
import { Badge, Empty, ErrorBox, INPUT, PageHeader, Td, Th, humanLabel } from "@/components/ui";
import { excerpt, fmtDate } from "@/lib/format";

export const dynamic = "force-dynamic";

const LEVELS = ["info", "warning", "error"];
const LIMIT = 50;

type SP = Record<string, string | string[] | undefined>;
const FILTER_KEYS = ["type", "level", "post_id", "source_id"];

export default async function ActivityPage({ searchParams }: { searchParams: SP }) {
  const sp = (k: string) => (typeof searchParams[k] === "string" ? (searchParams[k] as string) : "");
  const page = Math.max(parseInt(sp("page") || "1", 10) || 1, 1);

  const params = new URLSearchParams();
  for (const k of FILTER_KEYS) if (sp(k)) params.set(k, sp(k));
  params.set("limit", String(LIMIT));
  params.set("offset", String((page - 1) * LIMIT));

  let data: any = { items: [], total: 0 };
  let actions: any = { items: [] };
  let error = "";
  try {
    [data, actions] = await Promise.all([
      pubFetch(`/api/events?${params}`),
      pubFetch("/api/actions?limit=20"),
    ]);
  } catch (e: any) {
    error = e?.message ?? "нет связи с Control API";
  }

  const items: any[] = data?.items ?? [];
  const total: number = data?.total ?? 0;
  const totalPages = Math.max(Math.ceil(total / LIMIT), 1);

  const mkHref = (p: number) => {
    const q = new URLSearchParams();
    for (const k of FILTER_KEYS) if (sp(k)) q.set(k, sp(k));
    if (p > 1) q.set("page", String(p));
    const s = q.toString();
    return `/activity${s ? `?${s}` : ""}`;
  };

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Контроль" title="Журнал работы" description="События бота и команды из панели. Используйте фильтры, чтобы быстро найти причину проблемы." />
      {error && <ErrorBox message={error} />}

      <form action="/activity" method="get" className="filter-panel sm:grid-cols-2 lg:grid-cols-4">
        <label className="field-label lg:col-span-2">Событие
        <input
          name="type"
          defaultValue={sp("type")}
          placeholder="Например: ошибка публикации"
          className={INPUT}
        />
        <span className="field-help">Можно ввести технический код события, например publish_failed.</span></label>
        <label className="field-label">Важность<select name="level" defaultValue={sp("level")} className={INPUT}>
          <option value="">Все события</option>
          {LEVELS.map((l) => (
            <option key={l} value={l}>
              {humanLabel(l)}
            </option>
          ))}
        </select></label>
        <label className="field-label">Номер публикации
        <input
          name="post_id"
          defaultValue={sp("post_id")}
          placeholder="Например: 42"
          className={INPUT}
        />
        </label>
        <label className="field-label">Номер источника
        <input
          name="source_id"
          defaultValue={sp("source_id")}
          placeholder="Например: 3"
          className={INPUT}
        />
        </label>
        <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-3"><button className="button-primary">Показать события</button><Link href="/activity" className="button-secondary inline-flex items-center">Сбросить</Link></div>
      </form>

      {items.length === 0 && !error ? (
        <Empty>Событий по выбранным условиям пока нет.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="w-full">
            <thead>
              <tr>
                <Th>Время</Th>
                <Th>Уровень</Th>
                <Th>Событие</Th>
                <Th>Сообщение</Th>
                <Th>Публикация</Th>
                <Th>Источник</Th>
                <Th>Подробности</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id}>
                  <Td className="whitespace-nowrap text-xs text-zinc-500">{fmtDate(e.created_at)}</Td>
                  <Td>
                    <Badge v={e.level} />
                  </Td>
                  <Td className="whitespace-nowrap text-xs"><div className="font-medium text-slate-300">{humanLabel(e.type)}</div><div className="mt-0.5 font-mono text-[10px] text-slate-600">{e.type}</div></Td>
                  <Td className="max-w-[360px] text-xs text-zinc-400">{excerpt(e.message, 200)}</Td>
                  <Td>
                    {e.post_id ? (
                      <Link href={`/queue/${e.post_id}`} className="text-sky-400 hover:underline">
                        {e.post_id}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </Td>
                  <Td>{e.source_id ?? "—"}</Td>
                  <Td className="max-w-[240px] break-words text-xs text-zinc-600">
                    {e.metadata && Object.keys(e.metadata).length > 0
                      ? JSON.stringify(e.metadata).slice(0, 160)
                      : ""}
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-500">
          Событий: {total} · Страница {page} из {totalPages}
        </span>
        <div className="flex gap-2">
          {page > 1 && (
            <Link
              href={mkHref(page - 1)}
              className="button-secondary inline-flex items-center"
            >
              ← Назад
            </Link>
          )}
          {page < totalPages && (
            <Link
              href={mkHref(page + 1)}
              className="button-secondary inline-flex items-center"
            >
              Вперёд →
            </Link>
          )}
        </div>
      </div>

      <div><h2 className="text-lg font-semibold text-slate-100">Последние команды</h2><p className="mt-1 text-xs text-slate-400">Действия, запущенные пользователем через эту панель.</p></div>
      <div className="table-wrap">
        <table className="w-full">
          <thead>
            <tr>
              <Th>Создано</Th>
              <Th>Команда</Th>
              <Th>Статус</Th>
              <Th>Публикация</Th>
              <Th>Результат</Th>
            </tr>
          </thead>
          <tbody>
            {(actions?.items ?? []).map((a: any) => (
              <tr key={a.id}>
                <Td className="whitespace-nowrap text-xs text-zinc-500">{fmtDate(a.created_at)}</Td>
                <Td className="text-xs"><div>{humanLabel(a.kind)}</div><div className="font-mono text-[10px] text-slate-600">{a.kind}</div></Td>
                <Td>
                  <Badge v={a.status === "pending" ? "pending_action" : a.status} />
                </Td>
                <Td>{a.post_id ?? "—"}</Td>
                <Td className="max-w-[360px] break-words text-xs text-red-400">
                  {a.error ?? (a.result ? JSON.stringify(a.result).slice(0, 200) : "")}
                </Td>
              </tr>
            ))}
            {(actions?.items ?? []).length === 0 && (
              <tr>
                <Td className="text-xs text-zinc-500">нет действий</Td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
