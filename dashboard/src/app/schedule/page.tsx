import { pubFetch } from "@/lib/api";
import { ErrorBox, PageHeader } from "@/components/ui";
import ScheduleForm from "@/components/ScheduleForm";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function SchedulePage() {
  let data: any = null;
  let error = "";
  try {
    data = await pubFetch("/api/schedule");
  } catch (e: any) {
    error = e?.message ?? "нет связи с Control API";
  }
  return (
    <div>
      <PageHeader eyebrow="Автоматизация" title="Расписание" description="Выберите время публикаций и правила отбора материалов. Изменения применяются без перезапуска бота." />
      {error ? <ErrorBox message={error} /> : <ScheduleForm initial={data} />}
      <section className="mt-6 rounded-xl border border-white/10 p-5">
        <h2 className="text-lg font-semibold">Сеточные каналы</h2>
        <p className="mt-2 text-sm text-zinc-400">Расписание дополнительного канала, рекламных репостов и привязку аккаунтов для реакций можно изменить на отдельной странице.</p>
        <Link href="/additional" className="button-secondary mt-4 inline-flex items-center">Открыть дополнительные каналы</Link>
      </section>
    </div>
  );
}
