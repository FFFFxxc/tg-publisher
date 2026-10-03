import { pubFetch } from "@/lib/api";
import { Badge, Card, Empty, ErrorBox, PageHeader, Td, Th } from "@/components/ui";
import ActivityLoginForm from "@/components/ActivityLoginForm";
import ActionButton from "@/components/ActionButton";
import { fmtDate } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function AccountsPage() {
  let data: any = { items: [] };
  let error = "";
  try { data = await pubFetch("/api/activity-accounts"); }
  catch (e: any) { error = e?.message ?? "нет связи с Control API"; }
  const items: any[] = data?.items ?? [];

  return <div className="space-y-5">
    <PageHeader eyebrow="Автоматизация" title="Аккаунты для актива"
      description="Подключённые user-аккаунты входят в закрытую группу и ставят выбранную реакцию на новые публикации." />
    {error && <ErrorBox message={error} />}
    <Card title="Добавить аккаунт" description="Вход выполняется по номеру, коду Telegram и, если включён, паролю 2FA.">
      <ActivityLoginForm />
    </Card>
    {items.length === 0 && !error ? <Empty>аккаунтов пока нет — добавьте первый по номеру телефона</Empty> :
      <div className="table-wrap"><table className="w-full"><thead><tr>
        <Th>Аккаунт</Th><Th>Телефон</Th><Th>Telegram ID</Th><Th>Состояние</Th><Th>Последний актив</Th><Th>Действия</Th>
      </tr></thead><tbody>{items.map((a) => <tr key={a.id}>
        <Td>{a.display_name}</Td><Td className="font-mono text-xs">{a.phone_mask}</Td>
        <Td className="font-mono text-xs">{a.telegram_user_id}</Td>
        <Td><Badge v={a.enabled && a.status === "ready" ? "published" : a.status === "error" ? "error" : "skipped"}>
          {!a.enabled ? "Отключён" : a.status === "ready" ? "Готов" : "Ошибка"}
        </Badge>{a.last_error && <div className="mt-2 max-w-[260px] text-xs text-red-300">{a.last_error}</div>}</Td>
        <Td className="text-xs">{fmtDate(a.last_active_at)}</Td>
        <Td><div className="flex flex-wrap gap-2">
          <ActionButton path={`activity-accounts/${a.id}`} method="PATCH" body={{ enabled: !a.enabled }}
            label={a.enabled ? "Отключить" : "Включить"} doneLabel={a.enabled ? "отключён" : "включён"} />
          <ActionButton path={`activity-accounts/${a.id}/react`} label="Поставить реакции" doneLabel="реакции проверены" />
          <ActionButton path={`activity-accounts/${a.id}`} method="DELETE" label="Удалить" variant="danger"
            confirm={`Удалить аккаунт ${a.display_name} и его локальную сессию?`} doneLabel="удалён" />
        </div></Td>
      </tr>)}</tbody></table></div>}
    <p className="helper-copy">Автоматическая проверка запускается с заданным в конфигурации интервалом. Для каждого аккаунта, группы и сообщения результат фиксируется отдельно, поэтому уже обработанные публикации повторно не отправляются.</p>
  </div>;
}
