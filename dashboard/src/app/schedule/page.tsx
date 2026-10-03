import { pubFetch } from "@/lib/api";
import { ErrorBox } from "@/components/ui";
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
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-zinc-100">Расписание</h1>
      {error ? <ErrorBox message={error} /> : <ScheduleForm initial={data} />}
    </div>
  );
}
