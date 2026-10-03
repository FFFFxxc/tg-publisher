import type { ReactNode } from "react";

const COLORS: Record<string, string> = {
  candidate: "border-sky-500/25 bg-sky-500/10 text-sky-300", pending: "border-amber-500/25 bg-amber-500/10 text-amber-300", processing: "border-violet-500/25 bg-violet-500/10 text-violet-300", published: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300", failed: "border-red-500/25 bg-red-500/10 text-red-300", ambiguous: "border-orange-500/25 bg-orange-500/10 text-orange-300", skipped: "border-slate-500/25 bg-slate-500/10 text-slate-300", expired: "border-slate-500/20 bg-slate-500/10 text-slate-400", unchecked: "border-slate-500/25 bg-slate-500/10 text-slate-300", generated: "border-teal-500/25 bg-teal-500/10 text-teal-300", not_needed: "border-slate-500/20 bg-slate-500/10 text-slate-400", no_preview: "border-slate-500/20 bg-slate-500/10 text-slate-400", manual: "border-cyan-500/25 bg-cyan-500/10 text-cyan-300", parsed: "border-sky-500/25 bg-sky-500/10 text-sky-300", old: "border-fuchsia-500/25 bg-fuchsia-500/10 text-fuchsia-300", repost: "border-fuchsia-500/25 bg-fuchsia-500/10 text-fuchsia-300", error: "border-red-500/25 bg-red-500/10 text-red-300", warning: "border-amber-500/25 bg-amber-500/10 text-amber-300", info: "border-blue-500/25 bg-blue-500/10 text-blue-300", completed: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300", pending_action: "border-amber-500/25 bg-amber-500/10 text-amber-300",
};

export const STATUS_LABELS: Record<string, string> = {
  candidate: "Готов к отбору", pending: "Ожидает повтора", processing: "Обрабатывается", published: "Опубликован", failed: "Ошибка", ambiguous: "Нужно проверить", skipped: "Пропущен", expired: "Устарел", unchecked: "Не проверен", generated: "Текст готов", not_needed: "Не требуется", no_preview: "Нет превью", manual: "Изменён вручную", parsed: "Новый пост", old: "Из архива", repost: "Повторная публикация", error: "Ошибка", warning: "Предупреждение", info: "Информация", completed: "Выполнено", pending_action: "В очереди", publish_now: "Опубликовать сейчас", skip_post: "Пропустить пост", requeue_post: "Повторить обработку", generate_ai: "Создать текст AI", scan_own: "Обновить архив",
};

Object.assign(STATUS_LABELS, {
  photo: "Фото", video: "Видео", mixed: "Фото и видео / смешанный альбом", text: "Только текст", document: "Другой файл", unknown: "Формат уточняется",
  settings_updated: "Настройки сохранены", worker_started: "Бот запущен",
  source_collected: "Новые посты найдены", source_error: "Ошибка источника",
  source_added: "Источник добавлен", source_verified: "Источник проверен",
  source_backfilled: "Посты источника загружены", source_deleted: "Источник удалён",
  source_enabled: "Источник включён", source_disabled: "Источник выключен",
  own_scanned: "Архив обновлён", ai_generated: "Подпись создана", ai_failed: "Ошибка нейросети",
  publish_started: "Публикация началась", publish_completed: "Пост опубликован",
  publish_failed: "Публикация не удалась", publish_retry: "Назначен повтор",
  publish_ambiguous: "Результат отправки требует проверки",
  action_completed: "Команда выполнена", action_failed: "Ошибка команды",
  test_ai_provider: "Проверка нейросети", repost_own: "Повторить пост из архива",
  add_source: "Добавить источник", verify_source: "Проверить источник",
  backfill_source: "Загрузить посты источника", already_published: "Уже опубликован",
});
export function humanLabel(value?: string | null): string { if (!value) return "—"; return STATUS_LABELS[value] ?? value.replaceAll("_", " "); }
export function Badge({ v, children }: { v: string; children?: ReactNode }) { const cls = COLORS[v] ?? "border-slate-500/25 bg-slate-500/10 text-slate-300"; return <span className={`inline-flex items-center whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-semibold ${cls}`}>{children ?? humanLabel(v)}</span>; }
export function PageHeader({ eyebrow = "Publisher", title, description, action }: { eyebrow?: string; title: ReactNode; description?: ReactNode; action?: ReactNode }) { return <header className="page-header"><div><div className="page-eyebrow">{eyebrow}</div><h1 className="page-title">{title}</h1>{description ? <div className="page-description">{description}</div> : null}</div>{action}</header>; }
export function Card({ title, description, right, children, className = "" }: { title?: string; description?: string; right?: ReactNode; children: ReactNode; className?: string }) { return <section className={`surface p-4 sm:p-5 ${className}`}>{(title || right) && <div className="mb-4 flex flex-wrap items-start justify-between gap-3"><div>{title && <h2 className="text-[15px] font-semibold tracking-[-.01em] text-slate-100">{title}</h2>}{description && <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-400">{description}</p>}</div>{right}</div>}{children}</section>; }
export function Stat({ label, value, hint, tone = "default" }: { label: string; value: ReactNode; hint?: string; tone?: "default" | "good" | "warn" }) { const tones = { default: "from-slate-800/70 to-slate-900/40", good: "from-teal-950/70 to-slate-900/50", warn: "from-amber-950/60 to-slate-900/50" }; return <div className={`surface bg-gradient-to-br ${tones[tone]} p-4`}><div className="text-[11px] font-semibold uppercase tracking-[.08em] text-slate-500">{label}</div><div className="mt-2 break-words text-xl font-semibold tracking-[-.025em] text-slate-50">{value}</div>{hint && <div className="mt-1.5 text-xs leading-5 text-slate-400">{hint}</div>}</div>; }
export function Dot({ ok }: { ok: boolean }) { return <span className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? "bg-emerald-400 shadow-[0_0_0_4px_rgba(52,211,153,.1)]" : "bg-red-400 shadow-[0_0_0_4px_rgba(248,113,113,.1)]"}`} />; }
export function ErrorBox({ message }: { message: string }) { return <div role="alert" className="rounded-xl border border-red-500/25 bg-red-950/35 p-4 text-sm text-red-200"><div className="font-semibold">Не удалось выполнить запрос</div><div className="mt-1 text-xs leading-5 text-red-300/80">{message}</div></div>; }
export function Notice({ tone = "success", children }: { tone?: "success" | "warning"; children: ReactNode }) { return <div role="status" className={`rounded-xl border p-3 text-xs ${tone === "success" ? "border-emerald-500/25 bg-emerald-950/30 text-emerald-200" : "border-amber-500/25 bg-amber-950/30 text-amber-200"}`}>{children}</div>; }
export function Empty({ children }: { children: ReactNode }) { return <div className="rounded-2xl border border-dashed border-slate-700/70 bg-slate-900/25 p-10 text-center text-sm leading-6 text-slate-400">{children}</div>; }
export function Th({ children }: { children: ReactNode }) { return <th className="border-b border-slate-700/40 bg-slate-900/35 px-3 py-3 text-left text-[10px] font-bold uppercase tracking-[.08em] text-slate-500">{children}</th>; }
export function Td({ children, className }: { children: ReactNode; className?: string }) { return <td className={`border-b border-slate-800/70 px-3 py-3 align-top text-sm text-slate-300 ${className ?? ""}`}>{children}</td>; }
export const INPUT = "min-h-10 rounded-[10px] border border-slate-700/70 bg-slate-950/55 px-3 py-2 text-sm text-slate-100 shadow-inner shadow-black/10 outline-none placeholder:text-slate-600 hover:border-slate-600 focus:border-sky-500 focus:ring-2 focus:ring-sky-500/10 disabled:cursor-not-allowed disabled:opacity-50";
