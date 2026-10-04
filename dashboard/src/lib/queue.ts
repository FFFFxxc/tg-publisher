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

export function scoreLabel(score: unknown): string {
  if (score === null || score === undefined || score === "") return "—";
  const number = typeof score === "number" ? score : Number(score);
  return Number.isFinite(number) ? number.toFixed(2) : "—";
}
