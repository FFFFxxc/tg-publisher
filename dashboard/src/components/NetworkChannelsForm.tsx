"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Badge, Card, INPUT } from "@/components/ui";

type Account = { id: string; display_name: string; phone_mask: string; enabled: boolean; status: string };
type Binding = { account_id: string; enabled: boolean; next_run_at?: string | null; last_run_at?: string | null; status?: string | null; last_error?: string | null };
type Run = { slot: string; status: string; dest_msg_ids?: number[]; error?: string | null };
type Network = {
  id: "weekly" | "promo"; label: string; enabled: boolean; source_ref: string; target_ref: string;
  lookback_hours: number; times: string[]; min_posts?: number; max_posts?: number;
  caption_text?: string; caption_url?: string; emoji_id?: string; account_ids: string[];
  bindings?: Binding[]; recent_runs?: Run[];
};
type Payload = { items: Network[]; accounts: Account[]; reaction_interval_hours: number };
type Draft = Omit<Network, "times"> & { times_text: string };

function toDraft(item: Network): Draft { return { ...item, times_text: (item.times ?? []).join(", ") }; }
function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("ru-RU", { timeZone: "Europe/Moscow", dateStyle: "short", timeStyle: "short" });
}
const NETWORK_STATUS_LABELS: Record<string, string> = {
  ready: "Готов", processing: "В работе", completed: "Выполнено", published: "Опубликовано",
  no_new_posts: "Нет новых постов", skipped: "Пропущено", disabled: "Выключено",
  error: "Ошибка", failed: "Ошибка", pending: "Ожидает", waiting: "Ожидает запуска", success: "Успешно",
  sent: "Опубликовано", preparing: "Подготовка", sending: "Отправка", ambiguous: "Нужна проверка отправки",
};
function statusLabel(value?: string | null) { return value ? (NETWORK_STATUS_LABELS[value] ?? value.replaceAll("_", " ")) : "—"; }

export default function NetworkChannelsForm({ initial }: { initial: Payload }) {
  const [data, setData] = useState<Payload>(initial);
  const [drafts, setDrafts] = useState<Record<string, Draft>>(() => Object.fromEntries(initial.items.map((item) => [item.id, toDraft(item)])));
  const [baselines, setBaselines] = useState<Record<string, Draft>>(() => Object.fromEntries(initial.items.map((item) => [item.id, toDraft(item)])));
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<Record<string, string>>({});
  const [error, setError] = useState<Record<string, string>>({});
  const dirtyIds = useMemo(() => new Set(Object.keys(drafts).filter((id) => JSON.stringify(drafts[id]) !== JSON.stringify(baselines[id]))), [drafts, baselines]);
  const dirtyRef = useRef(dirtyIds.size > 0);
  useEffect(() => { dirtyRef.current = dirtyIds.size > 0; }, [dirtyIds.size]);

  useEffect(() => {
    if (dirtyIds.size) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch("/api/dash/networks", { cache: "no-store" });
        if (!response.ok) return;
        const next: Payload = await response.json();
        if (cancelled || dirtyRef.current) return;
        const mapped = Object.fromEntries(next.items.map((item) => [item.id, toDraft(item)]));
        setData(next); setDrafts(mapped); setBaselines(mapped);
      } catch { /* Следующее обновление повторит запрос. */ }
    }, 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [dirtyIds.size]);

  function update<K extends keyof Draft>(id: string, key: K, value: Draft[K]) {
    dirtyRef.current = true;
    setDrafts((current) => ({ ...current, [id]: { ...current[id], [key]: value } }));
    setMessage((current) => ({ ...current, [id]: "" }));
  }

  function toggleAccount(id: string, accountId: string, checked: boolean) {
    const current = drafts[id].account_ids ?? [];
    update(id, "account_ids", checked ? [...new Set([...current, accountId])] : current.filter((value) => value !== accountId));
  }

  async function save(event: FormEvent, id: string) {
    event.preventDefault(); setBusy(id); setMessage((v) => ({ ...v, [id]: "" })); setError((v) => ({ ...v, [id]: "" }));
    const draft = drafts[id];
    try {
      const body: Record<string, unknown> = {
        enabled: draft.enabled, source_ref: draft.source_ref.trim(), target_ref: draft.target_ref.trim(),
        lookback_hours: Number(draft.lookback_hours), times: draft.times_text.split(",").map((v) => v.trim()).filter(Boolean),
        account_ids: draft.account_ids,
      };
      if (id === "weekly") Object.assign(body, {
        min_posts: Number(draft.min_posts), max_posts: Number(draft.max_posts), caption_text: draft.caption_text ?? "",
        caption_url: draft.caption_url ?? "", emoji_id: String(draft.emoji_id ?? ""),
      });
      const response = await fetch(`/api/dash/networks/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result?.error || `Ошибка ${response.status}`);
      const saved: Network = result?.item ?? result?.network ?? result;
      const next = toDraft(saved.id ? saved : { ...draft, times: body.times as string[] });
      setDrafts((v) => ({ ...v, [id]: next })); setBaselines((v) => ({ ...v, [id]: next }));
      setData((v) => ({ ...v, items: v.items.map((item) => item.id === id ? (saved.id ? saved : { ...item, ...body } as Network) : item) }));
      setMessage((v) => ({ ...v, [id]: "Настройки сохранены и применены." }));
    } catch (e: any) { setError((v) => ({ ...v, [id]: e?.message ?? "Не удалось сохранить настройки" })); }
    finally { setBusy(null); }
  }

  return <div className="space-y-5">
    <Card title="Реакции аккаунтов" description={`Привязанные включённые аккаунты ставят реакции новым публикациям раз в ${data.reaction_interval_hours || 6} часов. Для каждого канала можно выбрать свой набор аккаунтов.`}>
      <div className="text-xs leading-5 text-slate-400">Отключённый аккаунт остаётся виден в настройках, но реакции не ставит, пока его снова не включат на странице «Аккаунты для актива».</div>
    </Card>
    {data.items.map((item) => {
      const draft = drafts[item.id]; if (!draft) return null;
      const bindings = item.bindings ?? [];
      return <form key={item.id} onSubmit={(event) => save(event, item.id)}>
        <Card title={item.label} description={item.id === "weekly" ? "Лучшие публикации закрытой группы отправляются в дополнительный канал." : "Рекламные репосты сеточного канала по отдельному расписанию."} right={<Badge v={draft.enabled ? "completed" : "skipped"}>{draft.enabled ? "Включён" : "Выключен"}</Badge>}>
          <fieldset disabled={busy !== null} className="space-y-5 disabled:opacity-70">
            <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-700/50 bg-slate-950/25 p-4 text-sm text-slate-200"><input className="mt-0.5 accent-teal-500" type="checkbox" checked={draft.enabled} onChange={(e) => update(item.id, "enabled", e.target.checked)} /><span><b className="block">Включить публикации</b><span className="mt-1 block text-xs text-slate-400">Выключение останавливает новые публикации и реакции для этого канала.</span></span></label>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="field-label">Источник<input value={draft.source_ref} onChange={(e) => update(item.id, "source_ref", e.target.value)} className={INPUT} /></label>
              <label className="field-label">Канал назначения<input value={draft.target_ref} onChange={(e) => update(item.id, "target_ref", e.target.value)} className={INPUT} /></label>
              <label className="field-label">Период отбора, часов<input type="number" min={1} value={draft.lookback_hours} onChange={(e) => update(item.id, "lookback_hours", Number(e.target.value))} className={INPUT} /></label>
              <label className="field-label">Время публикаций по Москве<input value={draft.times_text} onChange={(e) => update(item.id, "times_text", e.target.value)} placeholder="12:00, 16:00, 20:00" className={INPUT} /><span className="field-help">Укажите время через запятую.</span></label>
              {item.id === "weekly" && <>
                <label className="field-label">Минимум постов в день<input type="number" min={1} value={draft.min_posts ?? 1} onChange={(e) => update(item.id, "min_posts", Number(e.target.value))} className={INPUT} /></label>
                <label className="field-label">Максимум постов в день<input type="number" min={1} value={draft.max_posts ?? 3} onChange={(e) => update(item.id, "max_posts", Number(e.target.value))} className={INPUT} /></label>
                <label className="field-label md:col-span-2">Текст подписи<input value={draft.caption_text ?? ""} onChange={(e) => update(item.id, "caption_text", e.target.value)} className={INPUT} /></label>
                <label className="field-label">Ссылка в подписи<input type="url" value={draft.caption_url ?? ""} onChange={(e) => update(item.id, "caption_url", e.target.value)} className={INPUT} /></label>
                <label className="field-label">ID кастомного эмодзи<input inputMode="numeric" value={draft.emoji_id ?? ""} onChange={(e) => update(item.id, "emoji_id", e.target.value)} className={`${INPUT} font-mono`} /><span className="field-help">Сохраняется как строка без потери цифр.</span></label>
              </>}
            </div>
            <div className="rounded-xl border border-slate-700/50 bg-slate-950/20 p-4"><div className="text-xs font-semibold text-slate-300">Аккаунты для реакций каждые {data.reaction_interval_hours || 6} часов</div>
              <p className="mt-1 text-[11px] leading-5 text-slate-500">{item.id === "weekly" ? "Реакции ставятся публикациям в канале назначения." : "Реакции ставятся публикациям рекламируемого канала-источника."} Каждый аккаунт отмечает все новые посты за цикл. Уже отмеченные посты пропускаются.</p>
              <div className="mt-2 grid gap-3 lg:grid-cols-2">{data.accounts.map((account) => {
                const binding = bindings.find((value) => value.account_id === account.id);
                const selected = draft.account_ids.includes(account.id);
                const selectionBlocked = !account.enabled && !selected;
                return <label key={account.id} className={`rounded-xl border p-3 ${selectionBlocked ? "cursor-not-allowed border-slate-800/60 opacity-60" : "cursor-pointer border-slate-700/50"}`}>
                  <div className="flex gap-3"><input className="mt-1 accent-teal-500" type="checkbox" disabled={selectionBlocked} checked={selected} onChange={(e) => toggleAccount(item.id, account.id, e.target.checked)} /><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-200"><span>{account.display_name}</span><span className="font-mono text-xs font-normal text-slate-500">{account.phone_mask}</span>{!account.enabled && <Badge v="skipped">Отключён</Badge>}</div>
                    {account.enabled && draft.account_ids.includes(account.id) && <div className="mt-2 grid gap-1 text-[11px] text-slate-500"><span>Последняя проверка: {formatDate(binding?.last_run_at)}</span><span>Следующая проверка: {formatDate(binding?.next_run_at)}</span>{binding?.status && <span>Статус: {statusLabel(binding.status)}</span>}{binding?.last_error && <span className="text-red-300">Ошибка: {binding.last_error}</span>}</div>}
                  </div></div>
                </label>;
              })}</div>{!data.accounts.length && <p className="mt-2 text-xs text-amber-300">Сначала добавьте аккаунты на странице «Аккаунты для актива».</p>}</div>
            {!!item.recent_runs?.length && <div><h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Последние запуски</h3><div className="mt-2 grid gap-2">{item.recent_runs.slice(0, 5).map((run, index) => <div key={`${run.slot}-${index}`} className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800/80 px-3 py-2 text-xs text-slate-400"><span>{formatDate(run.slot)}</span><Badge v={run.status}>{statusLabel(run.status)}</Badge>{run.dest_msg_ids?.length ? <span>Сообщения: {run.dest_msg_ids.join(", ")}</span> : null}{run.error && <span className="text-red-300">{run.error}</span>}</div>)}</div></div>}
            <div className="flex flex-wrap items-center gap-3 border-t border-slate-700/40 pt-4"><button disabled={busy === item.id || !dirtyIds.has(item.id)} className="button-primary disabled:cursor-not-allowed disabled:opacity-50">{busy === item.id ? "Сохраняем…" : dirtyIds.has(item.id) ? "Сохранить канал" : "Изменения сохранены"}</button>{dirtyIds.has(item.id) && <span className="text-xs text-amber-300">Есть несохранённые изменения; автообновление приостановлено.</span>}{message[item.id] && <span role="status" className="text-xs text-emerald-300">{message[item.id]}</span>}{error[item.id] && <span role="alert" className="text-xs text-red-300">{error[item.id]}</span>}</div>
          </fieldset>
        </Card>
      </form>;
    })}
  </div>;
}
