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
      <section className="mt-6 rounded-xl border border-white/10 p-5">
        <h2 className="text-lg font-semibold">Реклама сеточного канала</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Каждый день в 14:00 и 20:00 по Москве — случайный пост из @anime_edit_videoo
          за последние 48 часов. Пересылка сохраняет исходный канал и подпись;
          ИИ и общий футер к ней не применяются. Уже использованные посты не повторяются.
          Если подходящих постов нет, слот пропускается. Общая пауза публикаций действует и на рекламу.
        </p>
        <p className="mt-3 text-sm text-zinc-400">
          Для обычных новых постов включённая ИИ-генерация запускается автоматически перед
          отправкой, а не при сборе в очередь. Заранее сгенерированная подпись используется повторно.
        </p>
      </section>
    </div>
  );
}
