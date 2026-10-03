import { pubFetch } from "@/lib/api";
import { Badge, Empty, ErrorBox, Td, Th } from "@/components/ui";
import AddSourceForm from "@/components/AddSourceForm";
import SourceRowActions from "@/components/SourceRowActions";
import { fmtDate } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function SourcesPage() {
  let data: any = { items: [] };
  let error = "";
  try {
    data = await pubFetch("/api/sources");
  } catch (e: any) {
    error = e?.message ?? "нет связи с Control API";
  }
  const items: any[] = data?.items ?? [];

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-zinc-100">Источники</h1>
      {error && <ErrorBox message={error} />}
      <AddSourceForm />

      {items.length === 0 && !error ? (
        <Empty>источников пока нет — добавьте первый через форму выше</Empty>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-[#10131a]">
          <table className="w-full">
            <thead>
              <tr>
                <Th>ID</Th>
                <Th>Канал</Th>
                <Th>Title</Th>
                <Th>Вкл</Th>
                <Th>Cursor</Th>
                <Th>Последняя ошибка</Th>
                <Th>Обновлён</Th>
                <Th>Действия</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id}>
                  <Td>{s.id}</Td>
                  <Td className="font-mono text-xs">{s.ref}</Td>
                  <Td>{s.title ?? "—"}</Td>
                  <Td>
                    <Badge v={s.enabled ? "published" : "skipped"}>{s.enabled ? "вкл" : "выкл"}</Badge>
                  </Td>
                  <Td>{s.last_message_id ?? "—"}</Td>
                  <Td className="max-w-[240px] text-xs text-red-400">{s.last_error ?? "—"}</Td>
                  <Td className="text-xs text-zinc-500">{fmtDate(s.updated_at)}</Td>
                  <Td>
                    <SourceRowActions s={s} />
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-zinc-500">
        Удаление доступно только без связанных постов (FK); иначе источник будет выключен. «Проверить» и
        «Забрать N» выполняются воркером как persistent actions — результат появится в статусе кнопки.
      </p>
    </div>
  );
}
