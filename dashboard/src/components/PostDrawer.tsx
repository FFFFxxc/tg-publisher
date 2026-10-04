"use client";

import { useEffect, useRef } from "react";
import MediaPreview from "@/components/MediaPreview";
import PostRowActions from "@/components/PostRowActions";
import { Badge, humanLabel } from "@/components/ui";
import { cleanPostText, excerpt, fmtDate } from "@/lib/format";
import { scoreLabel } from "@/lib/queue";

export default function PostDrawer({ post, onClose }: { post: any | null; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!post) return;
    const previous = document.activeElement as HTMLElement | null;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (panelRef.current?.querySelector("dialog[open]")) return;
        onClose();
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const nodes = [...panelRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')].filter(node => node.getClientRects().length > 0);
      if (!nodes.length) return;
      const first = nodes[0], last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => closeRef.current?.focus());
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; previous?.focus(); };
  }, [post?.id, onClose]);
  if (!post) return null;
  const text = cleanPostText(post.text, post.source_ref);
  return <div className="fixed inset-0 z-50" role="presentation">
    <button type="button" className="absolute inset-0 cursor-default bg-black/70" aria-label="Закрыть панель" onClick={onClose} />
    <aside ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="post-drawer-title" className="absolute inset-y-0 right-0 w-full max-w-2xl overflow-y-auto border-l border-slate-700 bg-[#081426] p-4 shadow-2xl sm:p-6">
      <div className="mb-5 flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-wider text-teal-300">Публикация</p><h2 id="post-drawer-title" className="mt-1 text-2xl font-bold text-white">Пост №{post.id}</h2></div><button ref={closeRef} type="button" onClick={onClose} className="button-secondary" aria-label="Закрыть панель поста">Закрыть</button></div>
      <div className="space-y-5">
        <MediaPreview postId={post.id} compact />
        <div className="flex flex-wrap items-center gap-2"><Badge v={post.status} /><span className="text-xs text-slate-400">{humanLabel(post.kind)} · {humanLabel(post.media_type || "unknown")}</span></div>
        <div className="flex flex-wrap justify-between gap-3 text-xs text-slate-400"><span>{post.source_ref}</span><span>{fmtDate(post.source_date)}</span></div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-950/40 p-4"><div className="text-xs font-semibold text-slate-400">Оценка материала</div><div className="mt-1 text-3xl font-bold text-teal-300" title="Score: 60% — ER относительно среднего источника, 40% — просмотры относительно среднего. ER учитывает реакции + 3×репосты + 2×комментарии на просмотр.">{scoreLabel(post.score)}</div></div>
        <p className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-200">{excerpt(text, 1200) || "Без подписи"}</p>
        <div className="flex flex-wrap gap-4 text-xs text-slate-400"><span>Просмотры: {post.views ?? 0}</span><span>Реакции: {post.reactions ?? 0}</span><span>Репосты: {post.forwards ?? 0}</span><span>Комментарии: {post.replies ?? 0}</span></div>
        {post.ai_caption && <div className="rounded-xl bg-slate-950/40 p-3"><div className="text-xs font-semibold text-slate-400">Подпись</div><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-200">{post.ai_caption}</p></div>}
        {post.last_error && <p role="alert" className="break-words rounded-xl border border-red-500/25 bg-red-950/30 p-3 text-xs text-red-300">{post.last_error}</p>}
        <div className="border-t border-slate-700/60 pt-4"><PostRowActions p={post} /></div>
      </div>
    </aside>
  </div>;
}
