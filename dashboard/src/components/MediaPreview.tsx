"use client";
import { useEffect, useRef, useState } from "react";
export default function MediaPreview({ postId, compact = false, thumbnail = false, src }: { postId: number | string; compact?: boolean; thumbnail?: boolean; src?: string }) {
 const imageUrl=src || `/api/dash/posts/${postId}/preview`;
 const [loaded,setLoaded]=useState(false),[missing,setMissing]=useState(false);const dialog=useRef<HTMLDialogElement>(null);const image=useRef<HTMLImageElement>(null);
 useEffect(()=>{setLoaded(!!image.current?.complete && !!image.current?.naturalWidth);setMissing(false)},[postId,src]);
 return <>
  <button type="button" disabled={missing||!loaded} onClick={()=>dialog.current?.showModal()} aria-label={`Увеличить изображение публикации №${postId}`} className={`relative block overflow-hidden rounded-xl border border-slate-700/50 bg-slate-950/70 ${thumbnail?"h-24 w-32 sm:h-28 sm:w-40":compact?"w-full h-40 sm:h-44":"w-full h-80 sm:h-[32rem]"}`}>
   {!loaded&&<span className="absolute inset-0 grid place-items-center text-sm text-slate-400">{missing?"Нет доступного изображения":"Загрузка изображения…"}</span>}
   {!missing&&<img ref={image} src={imageUrl} alt={`Публикация №${postId}`} loading="lazy" onLoad={()=>setLoaded(true)} onError={()=>setMissing(true)} className={`h-full w-full object-contain transition-opacity ${loaded?"opacity-100":"opacity-0"}`} />}
   {loaded&&!missing&&<span className="absolute bottom-3 right-3 inline-flex items-center gap-1.5 rounded-lg bg-slate-950/85 px-3 py-1.5 text-xs text-white"><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5M3 3l6 6M21 3l-6 6M3 21l6-6M21 21l-6-6" /></svg>{!thumbnail&&"Увеличить"}</span>}
  </button>
  <dialog ref={dialog} onClick={e=>{if(e.target===e.currentTarget)dialog.current?.close()}} className="m-auto h-[94dvh] w-[96vw] max-w-none overflow-hidden rounded-2xl border border-slate-600 bg-slate-950 p-3 text-white backdrop:bg-black/85">
   <div className="flex h-full flex-col gap-3"><div className="flex items-center justify-between"><span>Публикация №{postId}</span><button type="button" onClick={()=>dialog.current?.close()} className="button-secondary inline-flex items-center gap-2" aria-label="Закрыть изображение">Закрыть<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m6 6 12 12M18 6 6 18" /></svg></button></div><img src={imageUrl} alt={`Увеличенная публикация №${postId}`} className="min-h-0 w-full flex-1 object-contain" /></div>
  </dialog>
 </>;
}
