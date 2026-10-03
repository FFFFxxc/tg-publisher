import { pubFetch } from "@/lib/api";
import ActionButton from "@/components/ActionButton";
import { Empty, ErrorBox, Td, Th } from "@/components/ui";
import RepostButton from "@/components/RepostButton";
import { excerpt, fmtDate } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function OwnPostsPage() {
  let data: any = { items: [], total: 0 };
  let error = "";
  try {
    data = await pubFetch("/api/own?limit=50");
  } catch (e: any) {
    error = e?.message ?? "нет связи с Control API";
  }
  const items: any[] = data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold text-zinc-100">Свои посты ({data?.total ?? 0})</h1>
        <ActionButton path="own/scan" label="Сканировать канал" variant="primary" doneLabel="скан завершён" />
      </div>
      {error && <ErrorBox message={error} />}

      {items.length === 0 && !error ? (
        <Empty>
          снимок канала пуст — запустите «Сканировать канал» (или дождитесь планового скана старых постов)
        </Empty>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-[#10131a]">
          <table className="w-full">
            <thead>
              <tr>
                <Th>Дата</Th>
                <Th>Реакции</Th>
                <Th>Просмотры</Th>
                <Th>Репосты</Th>
                <Th>Последний репост</Th>
                <Th>Текст</Th>
                <Th>Действия</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((o) => (
                <tr key={o.group_key}>
                  <Td className="whitespace-nowrap text-xs text-zinc-500">{fmtDate(o.post_date)}</Td>
                  <Td>{o.reactions ?? 0}</Td>
                  <Td>{o.views ?? 0}</Td>
                  <Td>{o.forwards ?? 0}</Td>
                  <Td className="whitespace-nowrap text-xs text-zinc-500">{fmtDate(o.last_reposted_at)}</Td>
                  <Td className="max-w-[280px] text-xs text-zinc-400">{excerpt(o.text)}</Td>
                  <Td>
                    <RepostButton groupKey={o.group_key} />
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-zinc-500">
        «Репост» идёт через persistent action и штатный publish pipeline (та же защита от дублей). Сортировка —
        по реакциям, как и автоматический выбор «старых» постов.
      </p>
    </div>
  );
}
