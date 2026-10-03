import { pubFetch } from "@/lib/api";
import { ErrorBox, PageHeader } from "@/components/ui";
import FooterEditor from "@/components/FooterEditor";

export const dynamic = "force-dynamic";

export default async function FooterPage() {
  let data: any = null;
  let error = "";
  try {
    data = await pubFetch("/api/settings");
  } catch (e: any) {
    error = e?.message ?? "нет связи с Control API";
  }
  return (
    <div>
      <PageHeader eyebrow="Автоматизация" title="Подпись к постам" description="Настройте постоянные строки, которые бот добавляет в конец каждой новой публикации." />
      {error ? <ErrorBox message={error} /> : <FooterEditor initial={data} />}
    </div>
  );
}
