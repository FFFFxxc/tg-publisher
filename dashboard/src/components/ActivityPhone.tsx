"use client";

import { useState } from "react";

export default function ActivityPhone({ accountId, masked, enabled }: {
  accountId: string;
  masked?: string;
  enabled: boolean;
}) {
  const [phone, setPhone] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const visible = enabled && Boolean(phone);

  async function toggle() {
    if (visible) {
      setPhone("");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const res = await fetch(`/api/dash/activity-accounts/${encodeURIComponent(accountId)}/phone`,
        { cache: "no-store" });
      if (!res.ok) {
        throw new Error(res.status === 422 ? "Telegram не вернул номер."
          : res.status === 409 ? "Проверьте подключение аккаунта."
          : res.status === 504 ? "Telegram не ответил вовремя." : "Номер недоступен.");
      }
      const data = await res.json();
      if (typeof data?.phone !== "string" || !/^\+[1-9][0-9]{7,14}$/.test(data.phone)) {
        throw new Error("Получен некорректный ответ.");
      }
      setPhone(data.phone);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Номер недоступен.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="space-y-1 whitespace-nowrap">
    <div className="font-mono">{visible ? phone : masked || "—"}</div>
    {enabled && <button type="button" className="button-secondary" onClick={() => void toggle()}
      disabled={busy} aria-expanded={visible}>
      {busy ? "Загрузка…" : visible ? "Скрыть" : "Показать номер"}
    </button>}
    {error && enabled && <div role="status" className="whitespace-normal text-red-300">{error}</div>}
  </div>;
}
