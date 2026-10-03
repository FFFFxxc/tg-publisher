import Overview from "@/components/Overview";
import { ErrorBox, PageHeader } from "@/components/ui";
import { pubFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let data: any = null;
  let error = "";
  try {
    data = await pubFetch("/api/overview");
  } catch (e: any) {
    error = e?.message ?? "нет связи с Control API";
  }
  return (
    <div>
      <PageHeader eyebrow="Состояние системы" title="Главная" description="Всё важное о работе бота, ближайшей публикации и очереди — на одном экране." />
      {error ? <ErrorBox message={error} /> : <Overview initial={data} />}
    </div>
  );
}
