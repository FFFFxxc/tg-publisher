import Link from "next/link";
import { pubFetch } from "@/lib/api";
import { Badge, Empty, ErrorBox, Td, Th } from "@/components/ui";
import PostRowActions from "@/components/PostRowActions";
import { excerpt, fmtDate } from "@/lib/format";

export const dynamic = "force-dynamic";

const STATUSES = ["candidate", "pending", "processing", "published", "failed", "ambiguous", "skipped", "expired"];
const KINDS = ["parsed", "repost"];
const AI_STATUSES = ["unchecked", "processing", "generated", "not_needed", "no_preview", "failed", "manual"];
const FILTER_KEYS = ["status", "kind", "ai_status", "source_id", "date", "q"];
const LIMIT = 25;

type SP = Record<string, string | string[] | undefined>;

export default async function QueuePage({ searchParams }: { searchParams: SP }) {
  const sp = (k: string) => (typeof searchParams[k] === "string" ? (searchParams[k] as string) : "");
  const page = Math.max(parseInt(sp("page") || "1", 10) || 1, 1);

  const params = new URLSearchParams();
  for (const k of FILTER_KEYS) if (sp(k)) params.set(k, sp(k));
  params.set("limit", String(LIMIT));
  params.set("offset", String((page - 1) * LIMIT));

  let data: any = { items: [], total: 0 };
  let sources: any = { items: [] };
  let error = "";
  try {
    [data, sources] = await Promise.all([
      pubFetch(`/api/posts?${params}`),
      pubFetch("/api/sources?limit=100"),
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
    return `/queue${s ? `?${s}` : ""}`;
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-zinc-100">Очередь</h1>
      {error && <ErrorBox message={error} />}

      {/* GET-форма: смена фильтра сбрасывает pagination на первую страницу автоматически */}
      <form action="/queue" method="get" className="flex flex-wrap items-center gap-2">
        <select name="status" defaultValue={sp("status")} className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm">
          <option value="">статус: все</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select name="kind" defaultValue={sp("kind")} className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm">
          <option value="">kind: все</option>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <select name="ai_status" defaultValue={sp("ai_status")} className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm">
          <option value="">AI: все</option>
          {AI_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select name="source_id" defaultValue={sp("source_id")} className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm">
          <option value="">источник: все</option>
          {(sources?.items ?? []).map((s: any) => (
            <option key={s.id} value={s.id}>
              {s.ref}
            </option>
          ))}
        </select>
        <input
          type="date"
          name="date"
          defaultValue={sp("date")}
          className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm"
        />
        <input
          name="q"
          defaultValue={sp("q")}
          placeholder="поиск по тексту / id"
          className="w-56 rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm"
        />
        <button className="rounded border border-sky-700 bg-sky-800 px-3 py-1.5 text-sm hover:bg-sky-700">
          Фильтр
        </button>
        <Link href="/queue" className="text-xs text-zinc-500 hover:text-zinc-300">
          сброс
        </Link>
      </form>

      {items.length === 0 && !error ? (
        <Empty>ничего не найдено по текущим фильтрам</Empty>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-[#10131a]">
          <table className="w-full">
            <thead>
              <tr>
                <Th>ID</Th>
                <Th>Статус</Th>
                <Th>Kind</Th>
                <Th>Источник</Th>
                <Th>Дата</Th>
                <Th>Текст</Th>
                <Th>👀 / 🔺 / ⇄ / 💬</Th>
                <Th>AI</Th>
                <Th>Попытки</Th>
                <Th>Действия</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id}>
                  <Td>
                    <Link href={`/queue/${p.id}`} className="text-sky-400 hover:underline">
                      {p.id}
                    </Link>
                  </Td>
                  <Td>
                    <Badge v={p.status} />
                    {p.dest_msg_ids?.length > 0 && (
                      <div className="mt-0.5 text-xs text-emerald-400">dest: {p.dest_msg_ids.join(",")}</div>
                    )}
                  </Td>
                  <Td>
                    <Badge v={p.kind} />
                  </Td>
                  <Td className="font-mono text-xs">{p.source_ref}</Td>
                  <Td className="whitespace-nowrap text-xs text-zinc-500">{fmtDate(p.source_date)}</Td>
                  <Td className="max-w-[280px] text-xs text-zinc-400">{excerpt(p.text)}</Td>
                  <Td className="whitespace-nowrap text-xs text-zinc-400">
                    {p.views ?? 0} / {p.reactions ?? 0} / {p.forwards ?? 0} / {p.replies ?? 0}
                  </Td>
                  <Td>
                    <Badge v={p.ai_status} />
                    {p.ai_caption && <div className="mt-0.5 text-xs text-zinc-500">{excerpt(p.ai_caption, 60)}</div>}
                  </Td>
                  <Td>{p.attempts ?? 0}</Td>
                  <Td>
                    <PostRowActions p={p} />
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
    </div>
  );
}
