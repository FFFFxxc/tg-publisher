import type { ReactNode } from "react";
import PublisherIcon from "./PublisherIcon";

const COLORS: Record<string, string> = {
  candidate: "border-info-line bg-info-tint text-info", pending: "border-warning-line bg-warning-tint text-warning", processing: "border-line-strong bg-selected text-accent", published: "border-success-line bg-success-tint text-success", failed: "border-danger-line bg-danger-tint text-danger", ambiguous: "border-warning-line bg-warning-tint text-warning", skipped: "border-line bg-tint text-muted", expired: "border-line bg-tint text-muted", unchecked: "border-line bg-tint text-muted", generated: "border-line-strong bg-selected text-accent", not_needed: "border-line bg-tint text-muted", no_preview: "border-line bg-tint text-muted", manual: "border-info-line bg-info-tint text-info", parsed: "border-info-line bg-info-tint text-info", old: "border-line-strong bg-selected text-accent", repost: "border-line-strong bg-selected text-accent", error: "border-danger-line bg-danger-tint text-danger", warning: "border-warning-line bg-warning-tint text-warning", info: "border-info-line bg-info-tint text-info", completed: "border-success-line bg-success-tint text-success", pending_action: "border-warning-line bg-warning-tint text-warning",
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
export function Badge({ v, children }: { v: string; children?: ReactNode }) { const cls = COLORS[v] ?? "border-line bg-tint text-muted"; return <span className={`inline-flex items-center whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-semibold ${cls}`}>{children ?? humanLabel(v)}</span>; }
export function PageHeader({ eyebrow = "Publisher", title, description, action }: { eyebrow?: string; title: ReactNode; description?: ReactNode; action?: ReactNode }) { return <header className="page-header"><div><div className="page-eyebrow"><PublisherIcon name="dashboard" />{eyebrow}</div><h1 className="page-title">{title}</h1>{description ? <div className="page-description">{description}</div> : null}</div>{action}</header>; }
export function Card({ title, description, right, children, className = "" }: { title?: string; description?: string; right?: ReactNode; children: ReactNode; className?: string }) { return <section className={`surface p-4 sm:p-5 ${className}`}>{(title || right) && <div className="mb-4 flex flex-wrap items-start justify-between gap-3"><div>{title && <h2 className="text-base font-bold tracking-tight text-ink sm:text-lg">{title}</h2>}{description && <p className="mt-1 max-w-2xl text-xs leading-5 text-muted">{description}</p>}</div>{right}</div>}{children}</section>; }
export function Stat({ label, value, hint, tone = "default" }: { label: string; value: ReactNode; hint?: string; tone?: "default" | "good" | "warn" }) { const tones = { default: "", good: "!bg-success-tint", warn: "!bg-warning-tint" }; return <div className={`surface ${tones[tone]} p-4`}><div className="text-[11px] font-semibold uppercase tracking-[.08em] text-subtle">{label}</div><div className="mt-2 break-words text-xl font-semibold tracking-[-.025em] text-ink">{value}</div>{hint && <div className="mt-1.5 text-xs leading-5 text-muted">{hint}</div>}</div>; }
export function Dot({ ok }: { ok: boolean }) { return <span className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? "bg-success shadow-[0_0_0_4px_rgba(52,211,153,.1)]" : "bg-danger shadow-[0_0_0_4px_rgba(248,113,113,.1)]"}`} />; }
export function ErrorBox({ message }: { message: string }) { return <div role="alert" className="rounded-xl border border-danger-line bg-danger-tint p-4 text-sm text-danger"><div className="font-semibold">Не удалось выполнить запрос</div><div className="mt-1 text-xs leading-5 text-danger">{message}</div></div>; }
export function Notice({ tone = "success", children }: { tone?: "success" | "warning"; children: ReactNode }) { return <div role="status" className={`rounded-xl border p-3 text-xs ${tone === "success" ? "border-success-line bg-success-tint text-success" : "border-warning-line bg-warning-tint text-warning"}`}>{children}</div>; }
export function Empty({ children }: { children: ReactNode }) { return <div className="rounded-2xl border border-dashed border-line bg-tint p-10 text-center text-sm leading-6 text-muted">{children}</div>; }
export function Th({ children }: { children: ReactNode }) { return <th className="border-b border-line bg-tint px-3 py-3 text-left text-[10px] font-bold uppercase tracking-[.08em] text-subtle">{children}</th>; }
export function Td({ children, className }: { children: ReactNode; className?: string }) { return <td className={`border-b border-line px-3 py-3 align-top text-sm text-muted ${className ?? ""}`}>{children}</td>; }
export const INPUT = "min-h-10 min-w-0 rounded-[10px] border border-line-strong bg-paper px-3 py-2 text-sm text-ink outline-none placeholder:text-subtle hover:border-accent focus:border-accent focus:ring-2 focus:ring-accent disabled:cursor-not-allowed disabled:opacity-50";
