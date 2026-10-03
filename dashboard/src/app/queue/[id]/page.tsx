import Link from "next/link";
import { pubFetch } from "@/lib/api";
import { Badge, Card, ErrorBox, Td, Th } from "@/components/ui";
import PostRowActions from "@/components/PostRowActions";
import { fmtDate } from "@/lib/format";

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
          ← в очередь
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
        <Link href="/queue" className="text-sm text-sky-400 hover:underline">
          ← в очередь
        </Link>
        <PostRowActions p={p} />
      </div>

      <h1 className="text-xl font-semibold text-zinc-100">
        Пост {p.id} <Badge v={p.status} /> <Badge v={p.kind} /> <Badge v={p.ai_status} />
      </h1>

      <Card title="Поля">
        <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm md:grid-cols-3">
          {[
            ["Источник", `${p.source_ref}${p.source_title ? ` (${p.source_title})` : ""}`],
            ["Source msg ids", (p.source_msg_ids ?? []).join(", ")],
            ["Дата источника", fmtDate(p.source_date)],
            ["Создан", fmtDate(p.created_at)],
            ["Обновлён", fmtDate(p.updated_at)],
            ["Опубликован", fmtDate(p.published_at)],
            ["dest_msg_ids", (p.dest_msg_ids ?? []).join(", ") || "—"],
            ["send_started_at", fmtDate(p.send_started_at)],
            ["Попытки", String(p.attempts ?? 0)],
            ["👀 / 🔺 / ⇄ / 💬", `${p.views ?? 0} / ${p.reactions ?? 0} / ${p.forwards ?? 0} / ${p.replies ?? 0}`],
            ["Score", p.score != null ? String(p.score) : "—"],
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
            <div className="text-xs text-zinc-500">AI caption {p.ai_error ? `· ошибка: ${p.ai_error}` : ""}</div>
            <pre className="mt-1 whitespace-pre-wrap break-words rounded border border-zinc-800 bg-zinc-900/60 p-2 text-sm text-emerald-300">
              {p.ai_caption}
            </pre>
          </div>
        )}
      </Card>

      <Card title="События поста">
        {events.length === 0 ? (
          <div className="text-sm text-zinc-500">нет событий</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  <Th>Время</Th>
                  <Th>Уровень</Th>
                  <Th>Тип</Th>
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
                    <Td className="font-mono text-xs">{e.type}</Td>
                    <Td className="text-xs text-zinc-400">{e.message}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Действия над постом">
        {actions.length === 0 ? (
          <div className="text-sm text-zinc-500">нет действий</div>
        ) : (
          <div className="space-y-1.5">
            {actions.map((a) => (
              <div key={a.id} className="flex flex-wrap items-center gap-2 text-sm">
                <Badge v={a.status === "pending" ? "pending_action" : a.status} />
                <span className="font-mono text-xs text-zinc-400">{a.kind}</span>
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
