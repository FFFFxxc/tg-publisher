import { pubFetch } from "@/lib/api";
import { ErrorBox, PageHeader } from "@/components/ui";
import QueueBrowser from "@/components/QueueBrowser";

export const dynamic = "force-dynamic";

const FILTER_KEYS = ["status", "kind", "media_type", "ai_status", "source_id", "date", "q"] as const;
const LIMIT = 25;

type SP = Record<string, string | string[] | undefined>;

export default async function QueuePage({ searchParams }: { searchParams: SP }) {
  const sp = (k: string) => (typeof searchParams[k] === "string" ? (searchParams[k] as string) : "");
  const page = Math.max(parseInt(sp("page") || "1", 10) || 1, 1);

  const params = new URLSearchParams();
  for (const k of FILTER_KEYS) if (sp(k)) params.set(k, sp(k));
  if (!sp("status")) params.set("status", "queued");
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
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Контент" title="Очередь публикаций" description="Быстрый отбор материалов без длинных карточек. Подробности, подпись и время публикации открываются в боковой панели." />
      {error && <ErrorBox message={error} />}
      <QueueBrowser items={items} total={data?.total ?? 0} page={page} limit={LIMIT} sources={sources?.items ?? []}
        filters={{ ...Object.fromEntries(FILTER_KEYS.map(key => [key, sp(key)])), view: sp("view") }}
        initialView={sp("view") === "list" ? "list" : "grid"} hasError={Boolean(error)} />
    </div>
  );
}
