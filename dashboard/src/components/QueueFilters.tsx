import Link from "next/link";
import { INPUT } from "@/components/ui";
import { QUEUE_VIEWS, queueHref, queueViewHref, type QueueFilters as FilterValues } from "@/lib/queue";

export default function QueueFilters({ filters }: { filters: FilterValues }) {
  const active = filters.status || "candidate";
  const legacy = !QUEUE_VIEWS.some(view => view.value === active) ||
    Object.entries(filters).some(([key, value]) => value && !["status", "q", "view"].includes(key));

  return <section aria-label="Фильтры очереди" className="sticky top-[107px] z-20 -mx-1 rounded-2xl border border-slate-700/60 bg-[#091528]/95 p-3 shadow-xl shadow-black/20 backdrop-blur min-[901px]:top-2">
    <div className="flex flex-wrap items-center gap-3">
      <nav aria-label="Состояние публикаций" className="flex flex-wrap gap-2">
        {QUEUE_VIEWS.map(({ value, label }) => {
          const selected = active === value && !legacy;
          return <Link key={value} prefetch={false} href={queueViewHref(filters, value)} aria-current={selected ? "page" : undefined}
            className={`inline-flex min-h-10 items-center whitespace-nowrap rounded-full border px-3 text-xs font-semibold transition ${selected ? "border-teal-400/45 bg-teal-400/15 text-teal-200" : "border-slate-700/70 bg-slate-900/80 text-slate-300 hover:border-slate-500"}`}>{label}</Link>;
        })}
      </nav>
      <form key={queueHref(filters)} action="/queue" method="get" role="search" className="flex w-full items-center gap-2 md:ml-auto md:w-auto">
        {Object.entries(filters).filter(([key, value]) => key !== "q" && value).map(([key, value]) =>
          <input key={key} type="hidden" name={key} value={value} />)}
        <label htmlFor="queue-search" className="sr-only">Поиск по очереди</label>
        <input id="queue-search" name="q" type="search" defaultValue={filters.q} placeholder="Текст или номер" className={`${INPUT} min-w-0 flex-1 md:w-52`} />
        <button type="submit" className="button-secondary">Найти</button>
        {(filters.q || legacy) && <Link href={queueViewHref({ view: filters.view }, legacy ? "candidate" : active)} prefetch={false} className="text-xs font-semibold text-slate-400 hover:text-white">Сбросить</Link>}
      </form>
    </div>
    {legacy && <p className="mt-2 text-xs text-slate-400">Открыта сохранённая ссылка с дополнительными фильтрами. Выбери состояние, чтобы их сбросить.</p>}
  </section>;
}
