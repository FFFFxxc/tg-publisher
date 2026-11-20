export type QueueFilters = Record<string, string>;

export function queueHref(filters: QueueFilters, changes: QueueFilters = {}, page?: number): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries({ ...filters, ...changes })) {
    if (value && key !== "page") params.set(key, value);
  }
  if (page && page > 1) params.set("page", String(page));
  const query = params.toString();
  return `/queue${query ? `?${query}` : ""}`;
}

export const QUEUE_VIEWS = [
  { value: "candidate", label: "Готов к отбору" },
  { value: "failed", label: "Ошибка" },
  { value: "skipped", label: "Пропущен" },
  { value: "all", label: "Все" },
] as const;

export function queueViewHref(filters: QueueFilters, status: string): string {
  return queueHref({ status: status === "candidate" ? "" : status, q: filters.q, view: filters.view });
}

export function queueApiStatus(status: string): string {
  return status || "candidate";
}

export function scoreLabel(score: unknown): string {
  if (score === null || score === undefined || score === "") return "—";
  const number = typeof score === "number" ? score : Number(score);
  return Number.isFinite(number) ? number.toFixed(2) : "—";
}
