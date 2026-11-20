"use client";

import { useState } from "react";
import { fmtDate } from "@/lib/format";

type Result =
  | { status: "closed" | "loading" }
  | { status: "ready"; dates: string[] }
  | { status: "error"; message: string };

export default function ActivityNotifications({ accountId }: { accountId: string }) {
  const [result, setResult] = useState<Result>({ status: "closed" });
  const panelId = `telegram-notifications-${accountId}`;
  const open = result.status !== "closed";
  const loading = result.status === "loading";

  async function load() {
    setResult({ status: "loading" });
    try {
      const response = await fetch(`/api/dash/activity-accounts/${encodeURIComponent(accountId)}/notifications`,
        { cache: "no-store" });
      if (!response.ok) {
        throw new Error(response.status === 403 ? "Для просмотра уведомлений включите авторизацию панели."
          : response.status === 409 ? "Проверьте подключение аккаунта."
          : response.status === 504 ? "Telegram не ответил вовремя." : "Уведомления недоступны.");
      }
      const data = await response.json();
      if (!Array.isArray(data?.received_at) || !data.received_at.every(
        (value: unknown) => typeof value === "string" && Number.isFinite(Date.parse(value)))) {
        throw new Error("Получен некорректный ответ.");
      }
      setResult({ status: "ready", dates: data.received_at });
    } catch (error) {
      setResult({ status: "error", message: error instanceof Error ? error.message : "Уведомления недоступны." });
    }
  }

  return <div className={open ? "basis-full" : ""}>
    <button type="button" className="button-secondary" aria-expanded={open} aria-controls={panelId}
      disabled={loading} onClick={() => open ? setResult({ status: "closed" }) : void load()}>
      {open ? "Скрыть уведомления" : "Уведомления Telegram"}
    </button>
    <div id={panelId} hidden={!open} className="mt-2 space-y-2 text-xs">
      <p className="text-slate-400">До 10 последних уведомлений. Здесь видно время; текст — в приложении Telegram.</p>
      <div role="status">
        {loading && "Загрузка…"}
        {result.status === "error" && <span className="text-red-300">{result.message}</span>}
        {result.status === "ready" && (result.dates.length === 0 ? "Уведомлений пока нет."
          : <ul className="space-y-1">{result.dates.map((date, i) => <li key={`${date}-${i}`}>
            <time dateTime={date}>{fmtDate(date)}</time>
          </li>)}</ul>)}
      </div>
      {!loading && open && <button type="button" className="button-secondary" onClick={() => void load()}>
        Обновить
      </button>}
    </div>
  </div>;
}
