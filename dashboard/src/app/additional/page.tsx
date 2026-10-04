import { pubFetch } from "@/lib/api";
import { ErrorBox, PageHeader } from "@/components/ui";
import NetworkChannelsForm from "@/components/NetworkChannelsForm";

export const dynamic = "force-dynamic";

export default async function AdditionalPage() {
  let data: any = null;
  let error = "";
  try {
    data = await pubFetch("/api/networks");
  } catch (e: any) {
    error = e?.message ?? "нет связи с Control API";
  }
  return (
    <div>
      <PageHeader eyebrow="Автоматизация" title="Дополнительно" description="Управляйте сеточными каналами, расписанием публикаций и аккаунтами, которые ставят реакции." />
      {error ? <ErrorBox message={error} /> : <NetworkChannelsForm initial={data} />}
    </div>
  );
}
