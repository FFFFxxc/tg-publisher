import { pubFetch } from "@/lib/api";
import { Badge, Card, Empty, ErrorBox, PageHeader, Td, Th } from "@/components/ui";
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
    <div className="space-y-5">
      <PageHeader eyebrow="Контент" title="Источники" description="Каналы, из которых бот берёт материалы. Добавляйте, временно отключайте и проверяйте доступ." />
      {error && <ErrorBox message={error} />}
      <Card title="Добавить канал" description="Бот сначала проверит доступ, а затем сохранит источник."><AddSourceForm /></Card>

      {items.length === 0 && !error ? (
        <Empty>источников пока нет — добавьте первый через форму выше</Empty>
      ) : (
        <div className="table-wrap">
          <table className="w-full">
            <thead>
              <tr>
                <Th>ID</Th>
                <Th>Канал</Th>
                <Th>Название</Th>
                <Th>Состояние</Th>
                <Th>Последнее сообщение</Th>
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
                    <Badge v={s.enabled ? "published" : "skipped"}>{s.enabled ? "Активен" : "Отключён"}</Badge>
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
      <p className="helper-copy">
        Если у источника уже есть сохранённые материалы, удаление безопасно отключит его. Проверка доступа и загрузка прошлых публикаций могут занять некоторое время — результат появится рядом с кнопкой.
      </p>
    </div>
  );
}
