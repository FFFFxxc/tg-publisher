"use client";

import { useState } from "react";
import { fmtDate } from "@/lib/format";

type Result =
  | { status: "closed" | "loading" }
  | { status: "ready"; notifications: Notification[] }
  | { status: "error"; message: string };

type Notification = { received_at: string; text: string };

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
      if (!Array.isArray(data?.notifications) || !data.notifications.every((value: unknown) => {
        if (!value || typeof value !== "object") return false;
        const item = value as Record<string, unknown>;
        return typeof item.received_at === "string" && Number.isFinite(Date.parse(item.received_at))
          && typeof item.text === "string";
      })) {
        throw new Error("Получен некорректный ответ.");
      }
      setResult({ status: "ready", notifications: data.notifications });
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
      <p className="text-slate-400">До 10 последних уведомлений Telegram с датой и полным текстом.</p>
      <div role="status">
        {loading && "Загрузка…"}
        {result.status === "error" && <span className="text-red-300">{result.message}</span>}
        {result.status === "ready" && (result.notifications.length === 0 ? "Уведомлений пока нет."
          : <ul className="space-y-2">{result.notifications.map((notification, i) =>
          <li key={`${notification.received_at}-${i}`} className="rounded-lg border border-slate-700/60 bg-slate-950/40 p-3">
            <time className="block text-slate-500" dateTime={notification.received_at}>{fmtDate(notification.received_at)}</time>
            <p className="mt-1 whitespace-pre-wrap break-words text-slate-200">
              {notification.text || "Сообщение без текста"}
            </p>
          </li>)}</ul>)}
      </div>
      {!loading && open && <button type="button" className="button-secondary" onClick={() => void load()}>
        Обновить
      </button>}
    </div>
  </div>;
}
