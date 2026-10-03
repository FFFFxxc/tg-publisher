import Link from "next/link";
import { pubFetch } from "@/lib/api";
import { Badge, Empty, ErrorBox, INPUT, PageHeader, Td, Th, humanLabel } from "@/components/ui";
import PostRowActions from "@/components/PostRowActions";
import { excerpt, fmtDate } from "@/lib/format";
import MediaPreview from "@/components/MediaPreview";

export const dynamic = "force-dynamic";

const STATUSES = ["candidate", "pending", "processing", "published", "failed", "ambiguous", "skipped", "expired"];
const KINDS = ["parsed", "repost"];
const AI_STATUSES = ["unchecked", "processing", "generated", "not_needed", "no_preview", "failed", "manual"];
const FILTER_KEYS = ["status", "kind", "media_type", "ai_status", "source_id", "date", "q"];
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
    <div className="space-y-5">
      <PageHeader eyebrow="Контент" title="Очередь публикаций" description="Найдите материал, проверьте его состояние и запустите нужное действие. Фильтры можно сочетать." />
      {error && <ErrorBox message={error} />}

      {/* GET-форма: смена фильтра сбрасывает pagination на первую страницу автоматически */}
      <form action="/queue" method="get" className="filter-panel grid-cols-1 sm:grid-cols-2 xl:grid-cols-6">
        <label className="field-label">Состояние<select name="status" defaultValue={sp("status")} className={INPUT}>
          <option value="">Все состояния</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {humanLabel(s)}
            </option>
          ))}
        </select></label>
        <label className="field-label">Происхождение<select name="kind" defaultValue={sp("kind")} className={INPUT}>
          <option value="">Все типы</option>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {humanLabel(k)}
            </option>
          ))}
        </select></label>
        <label className="field-label">Формат материала<select name="media_type" defaultValue={sp("media_type")} className={INPUT}>
          <option value="">Фото и видео — все форматы</option>
          {["photo", "video", "mixed", "text", "document", "unknown"].map(k=><option key={k} value={k}>{humanLabel(k)}</option>)}
        </select></label>
        <label className="field-label">Текст AI<select name="ai_status" defaultValue={sp("ai_status")} className={INPUT}>
          <option value="">Любое состояние</option>
          {AI_STATUSES.map((s) => (
            <option key={s} value={s}>
              {humanLabel(s)}
            </option>
          ))}
        </select></label>
        <label className="field-label">Источник<select name="source_id" defaultValue={sp("source_id")} className={INPUT}>
          <option value="">Все источники</option>
          {(sources?.items ?? []).map((s: any) => (
            <option key={s.id} value={s.id}>
              {s.ref}
            </option>
          ))}
        </select></label>
        <label className="field-label">Дата<input
          type="date"
          name="date"
          defaultValue={sp("date")}
          className={INPUT}
        /></label>
        <label className="field-label">Поиск<input
          name="q"
          defaultValue={sp("q")}
          placeholder="Текст или номер"
          className={INPUT}
        /></label>
        <div className="flex items-end gap-2 sm:col-span-2 xl:col-span-6"><button className="button-primary">Показать результаты</button><Link href="/queue" className="button-secondary inline-flex items-center">Сбросить</Link></div>
      </form>

      {items.length === 0 && !error ? (
        <Empty>ничего не найдено по текущим фильтрам</Empty>
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 2xl:grid-cols-3">
          {items.map((p) => <article key={p.id} className="surface overflow-hidden">
            <MediaPreview postId={p.id} compact />
            <div className="space-y-4 p-5">
              <div className="flex flex-wrap items-center gap-2"><Link href={`/queue/${p.id}`} className="font-semibold text-sky-300">Пост №{p.id}</Link><Badge v={p.status}/><Badge v={p.kind}/><Badge v={p.media_type || "unknown"}/></div>
              <div className="flex flex-wrap justify-between gap-2 text-xs text-slate-400"><span>{p.source_ref}</span><span>{fmtDate(p.source_date)}</span></div>
              <p className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-200">{excerpt(p.text,280) || "Публикация без текста"}</p>
              <div className="flex flex-wrap gap-4 text-xs text-slate-400"><span>👁 {p.views ?? 0}</span><span>❤ {p.reactions ?? 0}</span><span>↗ {p.forwards ?? 0}</span><span>💬 {p.replies ?? 0}</span></div>
              <div className="rounded-xl bg-slate-950/40 p-3"><Badge v={p.ai_status}/>{p.ai_caption&&<p className="mt-2 text-xs leading-5 text-slate-400">{excerpt(p.ai_caption,160)}</p>}</div>
              {p.last_error&&<p className="break-words text-xs text-red-300">{excerpt(p.last_error,180)}</p>}
              <PostRowActions p={p}/>
            </div>
          </article>)}
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-500">
          Найдено: {total} · Страница {page} из {totalPages}
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
    </div>
  );
}
