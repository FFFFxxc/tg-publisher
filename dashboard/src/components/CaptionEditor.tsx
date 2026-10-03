"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { INPUT } from "@/components/ui";

export default function CaptionEditor({ p }: { p: any }) {
  const router = useRouter();
  const [text, setText] = useState(p.ai_caption ?? "");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  useEffect(() => { if (!dirty) setText(p.ai_caption ?? ""); }, [p.ai_caption, dirty]);
  useEffect(() => {
    if (dirty) return;
    const timer = setInterval(() => router.refresh(), 15000);
    return () => clearInterval(timer);
  }, [dirty, router]);
  async function save() {
    setBusy(true); setStatus("");
    try {
      const r = await fetch(`/api/dash/posts/${p.id}/caption`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ caption: text }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error ?? "Ошибка сохранения");
      setDirty(false); setStatus("Подпись сохранена вручную"); router.refresh();
    } catch (e: any) { setStatus(e.message); }
    finally { setBusy(false); }
  }
  return <div className="w-full space-y-2">
    <label className="field-label" htmlFor={`caption-${p.id}`}>Подпись к посту — можно изменить или ввести вручную</label>
    <textarea id={`caption-${p.id}`} className={INPUT} rows={4} maxLength={4096} value={text}
      placeholder="ИИ готовит подпись в очереди. Можно написать свою."
      onChange={e => { setText(e.target.value); setDirty(true); }} />
    <p className="text-xs text-slate-400">Ручной текст заменяет ИИ-подпись. Общий футер добавляется при публикации.</p>
    <button className="button-secondary" disabled={busy || !text.trim()} onClick={save}>
      {busy ? "Сохраняю…" : "Сохранить подпись"}
    </button>
    {status && <p role="status" className="text-sm">{status}</p>}
  </div>;
}
