"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, INPUT } from "@/components/ui";

type Item = { emoji?: string; emoji_id?: number | string | null; text: string; url?: string };

export default function FooterEditor({ initial }: { initial: any }) {
  const [items, setItems] = useState<Item[]>(() =>
    ((initial?.footer ?? []) as Item[]).map((x) => ({ ...x })),
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
      setMsg("сохранено — футер применится к следующим публикациям");
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
      <Card title="Строки подписи (порядок = порядок в сообщении)">
        <div className="space-y-3">
          {items.map((it, i) => (
            <div key={i} className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={it.emoji ?? ""}
                  onChange={(e) => update(i, { emoji: e.target.value })}
                  placeholder="emoji"
                  className={`w-20 ${INPUT}`}
                />
                <input
                  value={it.emoji_id ?? ""}
                  onChange={(e) =>
                    update(i, { emoji_id: e.target.value === "" ? null : (e.target.value as any) })
                  }
                  placeholder="custom emoji id (premium)"
                  className={`w-64 ${INPUT} font-mono text-xs`}
                />
                <input
                  value={it.text}
                  onChange={(e) => update(i, { text: e.target.value })}
                  placeholder="текст"
                  className={`w-56 ${INPUT}`}
                />
                <input
                  value={it.url ?? ""}
                  onChange={(e) => update(i, { url: e.target.value })}
                  placeholder="https://…"
                  className={`w-64 ${INPUT}`}
                />
                <div className="flex gap-1">
                  <button onClick={() => move(i, -1)} className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs">
                    ↑
                  </button>
                  <button onClick={() => move(i, 1)} className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs">
                    ↓
                  </button>
                  <button
                    onClick={() => setItems(items.filter((_, j) => j !== i))}
                    className="rounded border border-red-800 bg-red-900/70 px-2 py-1 text-xs text-red-200"
                  >
                    ✕
                  </button>
                </div>
              </div>
            </div>
          ))}
          <button
            onClick={() => setItems([...items, { emoji: "", emoji_id: null, text: "", url: "" }])}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs hover:bg-zinc-700"
          >
            + строка
          </button>
        </div>
      </Card>

      <Card title="Предпросмотр (текст)">
        <pre className="whitespace-pre-wrap rounded border border-zinc-800 bg-zinc-900/60 p-3 text-sm text-zinc-200">
          {preview || "—"}
        </pre>
        <p className="mt-2 text-xs text-zinc-500">
          UTF-16 offsets, premium custom emoji и защита от дубля футера считаются на воркере — существующая
          логика build_caption/render_footer не менялась. Дубль подписи не появится у постов, где она уже есть.
        </p>
      </Card>

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={busy || items.length === 0}
          className="rounded border border-sky-700 bg-sky-800 px-3 py-1.5 text-sm hover:bg-sky-700 disabled:opacity-50"
        >
          {busy ? "сохранение…" : "Сохранить"}
        </button>
        {msg && <span className="text-xs text-emerald-400">{msg}</span>}
        {err && <span className="text-xs text-red-400">{err}</span>}
      </div>
    </div>
  );
}
