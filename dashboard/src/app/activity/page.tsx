import Link from "next/link";
import { pubFetch } from "@/lib/api";
import { Badge, Empty, ErrorBox, Td, Th } from "@/components/ui";
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
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-zinc-100">Активность</h1>
      {error && <ErrorBox message={error} />}

      <form action="/activity" method="get" className="flex flex-wrap items-center gap-2">
        <input
          name="type"
          defaultValue={sp("type")}
          placeholder="тип (напр. publish_failed)"
          className="w-56 rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm"
        />
        <select name="level" defaultValue={sp("level")} className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm">
          <option value="">уровень: все</option>
          {LEVELS.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
        <input
          name="post_id"
          defaultValue={sp("post_id")}
          placeholder="post id"
          className="w-24 rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm"
        />
        <input
          name="source_id"
          defaultValue={sp("source_id")}
          placeholder="source id"
          className="w-24 rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm"
        />
        <button className="rounded border border-sky-700 bg-sky-800 px-3 py-1.5 text-sm hover:bg-sky-700">
          Фильтр
        </button>
        <Link href="/activity" className="text-xs text-zinc-500 hover:text-zinc-300">
          сброс
        </Link>
      </form>

      {items.length === 0 && !error ? (
        <Empty>событий пока нет</Empty>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-[#10131a]">
          <table className="w-full">
            <thead>
              <tr>
                <Th>Время</Th>
                <Th>Уровень</Th>
                <Th>Тип</Th>
                <Th>Сообщение</Th>
                <Th>Post</Th>
                <Th>Source</Th>
                <Th>Metadata</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id}>
                  <Td className="whitespace-nowrap text-xs text-zinc-500">{fmtDate(e.created_at)}</Td>
                  <Td>
                    <Badge v={e.level} />
                  </Td>
                  <Td className="whitespace-nowrap font-mono text-xs">{e.type}</Td>
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
          всего: {total} · страница {page} из {totalPages}
        </span>
        <div className="flex gap-2">
          {page > 1 && (
            <Link
              href={mkHref(page - 1)}
              className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs hover:bg-zinc-700"
            >
              ← Пред.
            </Link>
          )}
          {page < totalPages && (
            <Link
              href={mkHref(page + 1)}
              className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs hover:bg-zinc-700"
            >
              След. →
            </Link>
          )}
        </div>
      </div>

      <h2 className="pt-2 text-sm font-semibold text-zinc-300">Последние действия панели</h2>
      <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-[#10131a]">
        <table className="w-full">
          <thead>
            <tr>
              <Th>Создано</Th>
              <Th>Тип</Th>
              <Th>Статус</Th>
              <Th>Post</Th>
              <Th>Ошибка / результат</Th>
            </tr>
          </thead>
          <tbody>
            {(actions?.items ?? []).map((a: any) => (
              <tr key={a.id}>
                <Td className="whitespace-nowrap text-xs text-zinc-500">{fmtDate(a.created_at)}</Td>
                <Td className="font-mono text-xs">{a.kind}</Td>
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
