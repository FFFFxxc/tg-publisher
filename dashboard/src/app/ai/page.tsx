import { pubFetch } from "@/lib/api";
import { ErrorBox, PageHeader } from "@/components/ui";
import AiForm from "@/components/AiForm";

export const dynamic = "force-dynamic";

export default async function AiPage() {
  let data: any = null;
  let error = "";
  try {
    data = await pubFetch("/api/ai");
  } catch (e: any) {
    error = e?.message ?? "нет связи с Control API";
  }
  return (
    <div>
      <PageHeader eyebrow="Автоматизация" title="Нейросеть" description="Настройте два независимых AI-сервиса, вручную выберите активный и проверьте каждый до публикации." />
      {error ? <ErrorBox message={error} /> : <AiForm initial={data} />}
    </div>
  );
}
