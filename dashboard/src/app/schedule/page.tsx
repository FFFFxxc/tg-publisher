import { pubFetch } from "@/lib/api";
import { ErrorBox, PageHeader } from "@/components/ui";
import ScheduleForm from "@/components/ScheduleForm";

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
    </div>
  );
}
