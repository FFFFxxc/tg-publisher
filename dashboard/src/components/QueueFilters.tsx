"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { INPUT, humanLabel } from "@/components/ui";
import { isoToRuDate, ruDateToIso } from "@/lib/format";
import { queueHref, type QueueFilters as FilterValues } from "@/lib/queue";

const STATUSES = ["candidate", "pending", "processing", "published", "failed", "ambiguous", "skipped", "expired"];
const KINDS = ["parsed", "repost"];
const AI_STATUSES = ["unchecked", "processing", "generated", "not_needed", "no_preview", "failed", "manual"];
const MEDIA_TYPES = ["photo", "video", "mixed", "text", "document", "unknown"];

export default function QueueFilters({ filters, sources }: { filters: FilterValues; sources: any[] }) {
  const router = useRouter();
  const [search, setSearch] = useState(filters.q ?? "");
  const [date, setDate] = useState(isoToRuDate(filters.date));
  const [dateError, setDateError] = useState("");
  const pendingRef = useRef<FilterValues>({ ...filters });
  const searchRef = useRef(search);
  const dateRef = useRef(date);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const targetRef = useRef("");

  useEffect(() => {
    const arrived = queueHref(filters);
    if (targetRef.current && arrived !== targetRef.current) return;
    targetRef.current = "";
    pendingRef.current = { ...filters };
    searchRef.current = filters.q ?? "";
    dateRef.current = isoToRuDate(filters.date);
    setSearch(searchRef.current);
    setDate(dateRef.current);
  }, [filters]);
  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  function apply(changes: FilterValues) {
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    const pending: FilterValues = { ...pendingRef.current, q: searchRef.current.trim(), ...changes };
    const draftDate = ruDateToIso(dateRef.current);
    if (draftDate !== null && !("date" in changes)) pending.date = draftDate;
    pendingRef.current = pending;
    targetRef.current = queueHref(pending);
    router.push(targetRef.current);
  }

  function changeSearch(value: string) {
    setSearch(value);
    searchRef.current = value;
    pendingRef.current = { ...pendingRef.current, q: value.trim() };
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => apply({ q: value.trim() }), 450);
  }

  function changeDate(value: string) {
    setDate(value);
    dateRef.current = value;
    const iso = ruDateToIso(value);
    if (iso !== null) pendingRef.current = { ...pendingRef.current, date: iso };
  }

  function commitDate() {
    const iso = ruDateToIso(date);
    if (iso === null) { setDateError("Введите дату в формате ДД.ММ.ГГГГ"); return; }
    setDateError(""); apply({ date: iso });
  }

  const chip = (active: boolean) => `whitespace-nowrap rounded-full border px-3 py-2 text-xs font-semibold transition ${active ? "border-teal-400/45 bg-teal-400/15 text-teal-200" : "border-slate-700/70 bg-slate-900/80 text-slate-300 hover:border-slate-500"}`;
  return <section aria-label="Фильтры очереди" className="sticky top-[107px] z-20 -mx-1 rounded-2xl border border-slate-700/60 bg-[#091528]/95 p-3 shadow-xl shadow-black/20 backdrop-blur min-[901px]:top-2">
    <div className="flex items-center gap-2 overflow-x-auto pb-1">
      <button type="button" className={chip(filters.status === "candidate")} onClick={() => apply({ status: filters.status === "candidate" ? "" : "candidate" })}>Готов к отбору</button>
      <button type="button" className={chip(filters.media_type === "photo")} onClick={() => apply({ media_type: filters.media_type === "photo" ? "" : "photo" })}>Фото</button>
      <button type="button" className={chip(filters.media_type === "video")} onClick={() => apply({ media_type: filters.media_type === "video" ? "" : "video" })}>Видео</button>
      <label className="sr-only" htmlFor="queue-source">Источник</label>
      <select id="queue-source" value={filters.source_id ?? ""} onChange={e => apply({ source_id: e.target.value })} className={`${INPUT} min-h-9 min-w-48 rounded-full py-1 text-xs`}><option value="">Все источники</option>{sources.map(source => <option key={source.id} value={source.id}>{source.ref}</option>)}</select>
      {Object.entries(filters).some(([key, value]) => key !== "view" && Boolean(value)) && <button type="button" onClick={() => { if (timerRef.current) clearTimeout(timerRef.current); const next = { view: pendingRef.current.view ?? "" }; pendingRef.current = next; targetRef.current = queueHref(next); router.push(targetRef.current); }} className="whitespace-nowrap px-2 text-xs font-semibold text-slate-400 hover:text-white">Сбросить</button>}
    </div>
    <details className="mt-2 border-t border-slate-800/80 pt-2">
      <summary className="cursor-pointer select-none text-xs font-semibold text-slate-400 hover:text-slate-200">Дополнительные фильтры</summary>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <label className="field-label">Состояние<select value={filters.status ?? ""} onChange={e => apply({ status: e.target.value })} className={INPUT}><option value="">Все состояния</option>{STATUSES.map(value => <option key={value} value={value}>{humanLabel(value)}</option>)}</select></label>
        <label className="field-label">Происхождение<select value={filters.kind ?? ""} onChange={e => apply({ kind: e.target.value })} className={INPUT}><option value="">Все типы</option>{KINDS.map(value => <option key={value} value={value}>{humanLabel(value)}</option>)}</select></label>
        <label className="field-label">Формат<select value={filters.media_type ?? ""} onChange={e => apply({ media_type: e.target.value })} className={INPUT}><option value="">Все форматы</option>{MEDIA_TYPES.map(value => <option key={value} value={value}>{humanLabel(value)}</option>)}</select></label>
        <label className="field-label">Текст AI<select value={filters.ai_status ?? ""} onChange={e => apply({ ai_status: e.target.value })} className={INPUT}><option value="">Любое состояние</option>{AI_STATUSES.map(value => <option key={value} value={value}>{humanLabel(value)}</option>)}</select></label>
        <label className="field-label">Дата, ДД.ММ.ГГГГ<input inputMode="numeric" placeholder="04.10.2026" value={date} onChange={e => changeDate(e.target.value)} onBlur={commitDate} onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); commitDate(); } }} className={INPUT} />{dateError && <span role="alert" className="text-[11px] text-red-300">{dateError}</span>}</label>
        <label className="field-label">Поиск<input value={search} onChange={e => changeSearch(e.target.value)} placeholder="Текст или номер" className={INPUT} /></label>
      </div>
    </details>
  </section>;
}
