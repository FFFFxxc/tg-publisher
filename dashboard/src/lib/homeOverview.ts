const DATE_PARTS = { year: "numeric", month: "long", day: "numeric" } as const;
const CLOCK_PARTS = { hour: "2-digit", minute: "2-digit" } as const;
const MOSCOW = "Europe/Moscow";

export function homeDate(now: Date) {
  return new Intl.DateTimeFormat("ru-RU", { ...DATE_PARTS, timeZone: MOSCOW })
    .formatToParts(now).filter(p => ["day", "month", "year"].includes(p.type)).map(p => p.value).join(" ");
}

export function homeSlot(
  post: { selection?: string; scheduled_at?: string; due_at?: string } | null | undefined,
  schedule: { paused?: boolean; next_slot?: string },
  waiting: boolean,
  now = new Date(),
) {
  if (schedule.paused) return { value: "На паузе", tone: "warning" } as const;
  if (waiting) return { value: "Автопубликации ждут", tone: "warning" } as const;
  const value = post?.scheduled_at || post?.due_at || schedule.next_slot;
  if (!value) return null;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  const time = new Intl.DateTimeFormat("ru-RU", { ...CLOCK_PARTS, timeZone: MOSCOW }).format(date);
  const day = homeDate(date) === homeDate(now) ? "Сегодня" : homeDate(date).replace(/ \d{4}$/, "");
  return { value: `${day}, ${time}`, tone: "neutral" } as const;
}
