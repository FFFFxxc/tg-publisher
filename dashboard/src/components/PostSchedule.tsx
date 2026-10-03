"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { INPUT } from "@/components/ui";
function inputTime(raw?: string) { return raw ? new Date(new Date(raw).getTime()+3*3600000).toISOString().slice(0,16) : ""; }
export default function PostSchedule({ p }: { p: any }) {
 const [open,setOpen]=useState(false),[value,setValue]=useState(inputTime(p.scheduled_at)),[saved,setSaved]=useState(p.scheduled_at),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const router=useRouter();
 async function save(cancel=false) {
  setError("");
  const date=value ? new Date(value+":00+03:00") : null;
  if(!cancel && (!date || !Number.isFinite(date.getTime()) || date.getTime()<=Date.now())){setError("Выберите будущую дату и время");return;}
  setBusy(true);
  try {
   const scheduled_at=cancel?null:date!.toISOString();
   const r=await fetch(`/api/dash/posts/${p.id}/schedule`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({scheduled_at})});
   const d=await r.json();if(!r.ok)throw new Error(d.error||"Не удалось сохранить время");
   setSaved(d.scheduled_at);setOpen(false);router.refresh();
  }catch(e:any){setError(e.message);}finally{setBusy(false);}
 }
 return <div className="w-full space-y-2 border-t border-slate-700/50 pt-3">
  {saved && <div className="text-xs font-semibold text-teal-300">Запланировано: {new Date(saved).toLocaleString("ru-RU",{timeZone:"Europe/Moscow",dateStyle:"short",timeStyle:"short"})} МСК</div>}
  <button type="button" onClick={()=>setOpen(!open)} className="button-secondary">{saved?"Перенести публикацию":"Выбрать время публикации"}</button>
  {open && <div className="space-y-2 rounded-xl border border-teal-500/20 bg-slate-950/60 p-3">
   <label className="field-label">Дата и время по Москве<input type="datetime-local" value={value} onChange={e=>setValue(e.target.value)} className={`w-full ${INPUT}`} /></label>
   <p className="text-xs leading-5 text-slate-400">Пост выйдет в выбранное время, не раньше и независимо от общих слотов. Общая пауза бота действует и здесь.</p>
   <div className="flex flex-wrap gap-2"><button type="button" disabled={busy} onClick={()=>save()} className="button-primary">{busy?"Сохраняем…":"Запланировать"}</button>{saved&&<button type="button" disabled={busy} onClick={()=>save(true)} className="button-secondary">Отменить время</button>}</div>
  </div>}
  {error&&<div role="alert" className="text-xs text-red-300">{error}</div>}
 </div>;
}
