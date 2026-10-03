"use client";

import ActionButton from "@/components/ActionButton";
import { useState } from "react";
import { INPUT } from "@/components/ui";

export default function RepostButton({ groupKey }: { groupKey: string }) {
  const [open,setOpen]=useState(false),[value,setValue]=useState("");
  const date=value?new Date(value+":00+03:00"):null;
  const valid=!!date&&Number.isFinite(date.getTime())&&date.getTime()>Date.now();
  return (
    <div className="min-w-[220px] space-y-3">
    <ActionButton
      path="own/repost"
      body={{ group_key: groupKey }}
      label="Опубликовать снова"
      variant="primary"
      confirm="Опубликовать этот пост в канал сейчас?"
      doneLabel="добавлено в публикацию"
    />
    <button type="button" className="button-secondary" onClick={()=>setOpen(!open)}>Выбрать время публикации</button>
    {open&&<div className="space-y-3">
      <label className="field-label">Дата и время по Москве<input type="datetime-local" className={INPUT} value={value} onInput={e=>setValue(e.currentTarget.value)} onChange={e=>setValue(e.target.value)} /></label>
      {valid?<ActionButton path="own/repost" body={{group_key:groupKey,scheduled_at:date!.toISOString()}} label="Запланировать" variant="primary" confirm={`Запланировать повторную публикацию на ${value.replace("T"," ")} МСК?`} doneLabel="запланировано — время можно изменить в очереди" />:<p className="text-xs text-slate-400">Выберите будущую дату и время.</p>}
      <p className="text-xs text-slate-400">Пост появится в очереди с выбранным временем. Общая пауза бота действует и здесь.</p>
    </div>}
    </div>
  );
}
