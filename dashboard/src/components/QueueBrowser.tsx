"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import MediaPreview from "@/components/MediaPreview";
import PostDrawer from "@/components/PostDrawer";
import QueueFilters from "@/components/QueueFilters";
import { Badge, Empty, humanLabel } from "@/components/ui";
import { cleanPostText, excerpt, fmtDate } from "@/lib/format";
import { queueHref, scoreLabel, type QueueFilters as FilterValues } from "@/lib/queue";

type View = "grid" | "list";
function NeutralMeta({ kind, media }: { kind: string; media: string }) {
  return <span className="inline-flex items-center gap-1.5 text-xs text-slate-400" title={`${humanLabel(kind)}, ${humanLabel(media)}`}><svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 fill-none stroke-current" strokeWidth="1.8"><path d="M4 6.5h16v11H4zM8 3.5h8M8 20.5h8" /></svg>{humanLabel(kind)} · {humanLabel(media)}</span>;
}

export default function QueueBrowser({ items, total, page, limit, sources, filters, initialView, hasError }: { items: any[]; total: number; page: number; limit: number; sources: any[]; filters: FilterValues; initialView: View; hasError: boolean }) {
  const [view, setView] = useState<View>(initialView);
  const [selected, setSelected] = useState<any | null>(null);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has("view")) return;
    try { const saved = localStorage.getItem("queue-view"); if (saved === "grid" || saved === "list") setView(saved); } catch { /* private storage may be unavailable */ }
  }, []);
  useEffect(() => {
    if (!selected?.id) return;
    if (!items.some(item => item.id === selected.id)) { setSelected(null); return; }
    let cancelled = false;
    fetch(`/api/dash/posts/${selected.id}`, { cache: "no-store" }).then(async response => {
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Не удалось загрузить пост");
      if (!cancelled && data.post) setSelected((current: any) => current?.id === selected.id ? { ...current, ...data.post, score: data.post.score ?? current.score } : current);
    }).catch(() => { /* карточка остается доступной с данными списка */ });
    return () => { cancelled = true; };
  }, [items, selected?.id]);
  function changeView(next: View) {
    setView(next);
    try { localStorage.setItem("queue-view", next); } catch { /* URL still preserves the choice */ }
    window.history.replaceState({ ...window.history.state }, "", queueHref(filters, { view: next }, page));
  }
  const closeDrawer = useCallback(() => setSelected(null), []);
  const totalPages = Math.max(Math.ceil(total / limit), 1);
  const cards = items.map(post => {
    const text = cleanPostText(post.text, post.source_ref);
    return <article key={post.id} className={`surface flex overflow-hidden ${view === "grid" ? "h-full flex-col" : "min-h-40 flex-col sm:flex-row"}`}>
      <div className={view === "grid" ? "shrink-0" : "shrink-0 sm:w-52"}><MediaPreview postId={post.id} compact /></div>
      <div className="flex min-w-0 flex-1 flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="font-semibold text-slate-100">Пост №{post.id}</span><Badge v={post.status} /></div><div className="mt-1"><NeutralMeta kind={post.kind} media={post.media_type || "unknown"} /></div></div><div tabIndex={0} aria-label={`Score ${scoreLabel(post.score)}. 60 процентов — ER относительно среднего источника, 40 процентов — просмотры относительно среднего`} className="shrink-0 text-right" title="Score: 60% — ER относительно среднего источника, 40% — просмотры относительно среднего. ER = (реакции + 3×репосты + 2×комментарии) / просмотры."><div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Score</div><div className="text-xl font-bold text-teal-300">{scoreLabel(post.score)}</div></div></div>
        <div className="flex flex-wrap justify-between gap-2 text-[11px] text-slate-500"><span className="truncate">{post.source_ref}</span><span>{fmtDate(post.source_date)}</span></div>
        <p className={`break-words text-sm leading-5 text-slate-300 ${view === "grid" ? "line-clamp-3" : "line-clamp-2"}`}>{excerpt(text, view === "grid" ? 220 : 320) || "Без подписи"}</p>
        <div className="mt-auto flex items-center justify-between gap-3 border-t border-slate-700/50 pt-3"><span className="text-[11px] text-slate-500">{post.views ?? 0} просмотров · {post.reactions ?? 0} реакций</span><button type="button" onClick={() => setSelected(post)} className="button-secondary">Детали</button></div>
      </div>
    </article>;
  });
  return <>
    <QueueFilters filters={filters} sources={sources} />
    <div className="flex items-center justify-between gap-3"><p className="text-xs text-slate-500">Найдено: {total}</p><div className="flex rounded-xl border border-slate-700/70 bg-slate-950/40 p-1" role="group" aria-label="Вид очереди"><button type="button" aria-pressed={view === "grid"} onClick={() => changeView("grid")} className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${view === "grid" ? "bg-slate-700 text-white" : "text-slate-400"}`}>Плитка</button><button type="button" aria-pressed={view === "list"} onClick={() => changeView("list")} className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${view === "list" ? "bg-slate-700 text-white" : "text-slate-400"}`}>Список</button></div></div>
    {items.length === 0 && !hasError ? <Empty>ничего не найдено по текущим фильтрам</Empty> : <div className={view === "grid" ? "grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4" : "grid gap-3"}>{cards}</div>}
    <div className="flex items-center justify-between"><span className="text-xs text-slate-500">Страница {page} из {totalPages}</span><div className="flex gap-2">{page > 1 && <Link href={queueHref(filters, { view }, page - 1)} className="button-secondary inline-flex items-center">← Назад</Link>}{page < totalPages && <Link href={queueHref(filters, { view }, page + 1)} className="button-secondary inline-flex items-center">Вперёд →</Link>}</div></div>
    <PostDrawer post={selected} onClose={closeDrawer} />
  </>;
}
