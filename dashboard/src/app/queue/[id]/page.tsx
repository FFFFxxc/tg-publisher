import Link from "next/link";
import { pubFetch } from "@/lib/api";
import { Badge, Card, ErrorBox, PageHeader, Td, Th, humanLabel } from "@/components/ui";
import PostRowActions from "@/components/PostRowActions";
import { fmtDate } from "@/lib/format";
import MediaPreview from "@/components/MediaPreview";

export const dynamic = "force-dynamic";

export default async function PostDetailPage({ params }: { params: { id: string } }) {
  let data: any = null;
  let error = "";
  try {
    data = await pubFetch(`/api/posts/${params.id}`);
  } catch (e: any) {
    error = e?.message ?? "не удалось загрузить пост";
  }

  if (error || !data?.post) {
    return (
      <div className="space-y-4">
        <Link href="/queue" className="text-sm text-sky-400 hover:underline">
          ← Вернуться в очередь
        </Link>
        <ErrorBox message={error || "пост не найден"} />
      </div>
    );
  }

  const p = data.post;
  const events: any[] = data.events ?? [];
  const actions: any[] = data.actions ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Link href="/queue" className="text-sm text-sky-300 hover:underline">
          ← Вернуться в очередь
        </Link>
        <PostRowActions p={p} />
      </div>

      <PageHeader eyebrow="Очередь публикаций" title={`Публикация №${p.id}`} description={<span className="flex flex-wrap gap-2"><Badge v={p.status} /><Badge v={p.kind} /><Badge v={p.ai_status} /></span>} />

      <Card title="Изображение" description="Превью исходного медиафайла. Оно загружается только при открытии страницы.">
        <div className="max-w-3xl"><MediaPreview postId={p.id} /></div>
      </Card>

      <Card title="Сведения о публикации">
        <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm md:grid-cols-3">
          {[
            ["Источник", `${p.source_ref}${p.source_title ? ` (${p.source_title})` : ""}`],
            ["Сообщения в источнике", (p.source_msg_ids ?? []).join(", ")],
            ["Дата источника", fmtDate(p.source_date)],
            ["Добавлен в очередь", fmtDate(p.created_at)],
            ["Последнее изменение", fmtDate(p.updated_at)],
            ["Время публикации", fmtDate(p.published_at)],
            ["Сообщения в вашем канале", (p.dest_msg_ids ?? []).join(", ") || "—"],
            ["Начало отправки", fmtDate(p.send_started_at)],
            ["Попытки", String(p.attempts ?? 0)],
            ["Просмотры / реакции / репосты / ответы", `${p.views ?? 0} / ${p.reactions ?? 0} / ${p.forwards ?? 0} / ${p.replies ?? 0}`],
            ["Рейтинг материала", p.score != null ? String(p.score) : "—"],
            ["Последняя ошибка", p.last_error ?? "—"],
          ].map(([k, v]) => (
            <div key={k}>
              <div className="text-xs text-zinc-500">{k}</div>
              <div className="break-words text-zinc-300">{v}</div>
            </div>
          ))}
        </div>
        <div className="mt-3">
          <div className="text-xs text-zinc-500">Текст</div>
          <pre className="mt-1 whitespace-pre-wrap break-words rounded border border-zinc-800 bg-zinc-900/60 p-2 text-sm text-zinc-300">
            {p.text || "—"}
          </pre>
        </div>
        {p.ai_caption && (
          <div className="mt-3">
            <div className="text-xs text-zinc-500">Текст, созданный AI {p.ai_error ? `· ошибка: ${p.ai_error}` : ""}</div>
            <pre className="mt-1 whitespace-pre-wrap break-words rounded border border-zinc-800 bg-zinc-900/60 p-2 text-sm text-emerald-300">
              {p.ai_caption}
            </pre>
          </div>
        )}
      </Card>

      <Card title="История публикации">
        {events.length === 0 ? (
          <div className="text-sm text-zinc-500">нет событий</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  <Th>Время</Th>
                  <Th>Уровень</Th>
                  <Th>Событие</Th>
                  <Th>Сообщение</Th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id}>
                    <Td className="whitespace-nowrap text-xs text-zinc-500">{fmtDate(e.created_at)}</Td>
                    <Td>
                      <Badge v={e.level} />
                    </Td>
                    <Td className="text-xs"><div>{humanLabel(e.type)}</div><div className="font-mono text-[10px] text-slate-600">{e.type}</div></Td>
                    <Td className="text-xs text-zinc-400">{e.message}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Запущенные команды">
        {actions.length === 0 ? (
          <div className="text-sm text-zinc-500">нет действий</div>
        ) : (
          <div className="space-y-1.5">
            {actions.map((a) => (
              <div key={a.id} className="flex flex-wrap items-center gap-2 text-sm">
                <Badge v={a.status === "pending" ? "pending_action" : a.status} />
                <span className="text-xs text-zinc-300">{humanLabel(a.kind)}</span>
                <span className="text-xs text-zinc-500">{fmtDate(a.created_at)}</span>
                {a.error && <span className="text-xs text-red-400">{a.error}</span>}
                {a.result && (
                  <span className="text-xs text-zinc-500">{JSON.stringify(a.result).slice(0, 200)}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
