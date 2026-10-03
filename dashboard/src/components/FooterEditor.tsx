"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, INPUT } from "@/components/ui";

type Item = { emoji?: string; emoji_id?: string | null; text: string; url?: string };

export default function FooterEditor({ initial }: { initial: any }) {
  const [items, setItems] = useState<Item[]>(() =>
    ((initial?.footer ?? []) as Array<Omit<Item, "emoji_id"> & { emoji_id?: string | number | null }>).map((x) => ({
      ...x,
      emoji_id: x.emoji_id == null ? null : String(x.emoji_id),
    })),
  );
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  function update(i: number, patch: Partial<Item>) {
    setItems(items.map((it, j) => (i === j ? { ...it, ...patch } : it)));
  }

  function move(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= items.length) return;
    const copy = [...items];
    [copy[i], copy[j]] = [copy[j], copy[i]];
    setItems(copy);
  }

  async function save() {
    setBusy(true);
    setMsg("");
    setErr("");
    try {
      const res = await fetch("/api/dash/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ footer: items }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.error || `ошибка ${res.status}`);
      setMsg("Подпись сохранена и появится в следующих публикациях.");
      router.refresh();
    } catch (e: any) {
      setErr(e?.message ?? "ошибка");
    } finally {
      setBusy(false);
    }
  }

  const preview = items
    .map((it) => `${it.emoji ? `${it.emoji} ` : ""}${it.text ?? ""}`)
    .join("\n");

  return (
    <div className="space-y-4">
      <Card title="Строки подписи" description="Перетаскивание пока не требуется: меняйте порядок кнопками со стрелками. Каждая строка может быть ссылкой.">
        <div className="space-y-3">
          {items.map((it, i) => (
            <div key={i} className="rounded-xl border border-slate-700/50 bg-slate-950/25 p-4">
              <div className="mb-3 text-xs font-semibold text-slate-400">Строка {i + 1}</div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[100px_1fr_1fr_auto]">
                <label className="field-label">Эмодзи
                <input
                  value={it.emoji ?? ""}
                  onChange={(e) => update(i, { emoji: e.target.value })}
                  placeholder="👀"
                  className={`w-full ${INPUT}`}
                />
                </label>
                <label className="field-label">Текст
                <input value={it.text} onChange={(e) => update(i, { text: e.target.value })} placeholder="Например: Больше контента" className={`w-full ${INPUT}`} />
                </label>
                <label className="field-label">Ссылка
                <input value={it.url ?? ""} onChange={(e) => update(i, { url: e.target.value })} placeholder="https://…" className={`w-full ${INPUT}`} />
                </label>
                <div className="flex items-end gap-1">
                  <button aria-label="Поднять строку" onClick={() => move(i, -1)} className="button-secondary">↑</button>
                  <button aria-label="Опустить строку" onClick={() => move(i, 1)} className="button-secondary">↓</button>
                  <button aria-label="Удалить строку" onClick={() => setItems(items.filter((_, j) => j !== i))} className="button-danger">✕</button>
                </div>
                <label className="field-label sm:col-span-2 xl:col-span-4">ID премиум-эмодзи <span className="field-help">Необязательно. Оставьте пустым для обычного эмодзи.</span>
                <input
                  value={it.emoji_id ?? ""}
                  onChange={(e) =>
                    update(i, { emoji_id: e.target.value === "" ? null : e.target.value })
                  }
                  placeholder="Полный числовой ID без сокращений"
                  className={`${INPUT} w-full font-mono text-xs`}
                />
                </label>
              </div>
            </div>
          ))}
          <button
            onClick={() => setItems([...items, { emoji: "", emoji_id: null, text: "", url: "" }])}
            className="button-secondary"
          >
            + Добавить строку
          </button>
        </div>
      </Card>

      <Card title="Предпросмотр" description="Так текст будет выглядеть в конце сообщения. Ссылки в предпросмотре не открываются.">
        <pre className="min-h-24 whitespace-pre-wrap rounded-xl border border-slate-700/50 bg-slate-950/50 p-4 text-sm leading-6 text-slate-200">
          {preview || "—"}
        </pre>
        <p className="mt-2 text-xs text-zinc-500">
          Бот автоматически подготовит ссылки и премиум-эмодзи. Если подпись уже есть в исходном посте, второй раз она не добавится.
        </p>
      </Card>

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={busy || items.length === 0}
          className="button-primary disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? "Сохраняем…" : "Сохранить подпись"}
        </button>
        {msg && <span className="text-xs text-emerald-400">{msg}</span>}
        {err && <span className="text-xs text-red-400">{err}</span>}
      </div>
    </div>
  );
}
