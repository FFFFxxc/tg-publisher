export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("ru-RU", {
    timeZone: "Europe/Moscow",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function excerpt(s: string | null | undefined, n = 160): string {
  const t = (s ?? "").replace(/\s+/g, " ").trim();
  return t.length > n ? t.slice(0, n - 1) + "…" : t;
}

export function fmtAge(seconds?: number | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const n = Math.floor(seconds);
  if (n < 60) return `${n} с назад`;
  if (n < 3600) return `${Math.floor(n / 60)} мин назад`;
  if (n < 86400) return `${Math.floor(n / 3600)} ч${n % 3600 >= 60 ? ` ${Math.floor(n % 3600 / 60)} мин` : ""} назад`;
  return `${Math.floor(n / 86400)} дн назад`;
}

export function cleanPostText(text?: string | null, sourceRef?: string | null): string {
  const source = (sourceRef ?? "").replace(/^https?:\/\/(?:www\.)?t\.me\//i, "").replace(/^@/, "").replace(/\/$/, "").toLowerCase();
  if (source !== "awebm") return (text ?? "").trim();
  return (text ?? "").split(/\r?\n/).filter(line => !/^\s*a\.webm\s*$/i.test(line)).join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export function isoToRuDate(value?: string | null): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value ?? "");
  return m ? `${m[3]}.${m[2]}.${m[1]}` : "";
}

export function ruDateToIso(value: string): string | null {
  if (!value.trim()) return "";
  const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value.trim());
  if (!m) return null;
  const iso = `${m[3]}-${m[2]}-${m[1]}`;
  const d = new Date(iso + "T00:00:00Z");
  return Number.isFinite(d.getTime()) && d.toISOString().slice(0, 10) === iso ? iso : null;
}
