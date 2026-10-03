import { pubFetch } from "@/lib/api";
import { ErrorBox } from "@/components/ui";
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
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-zinc-100">Подпись (footer)</h1>
      {error ? <ErrorBox message={error} /> : <FooterEditor initial={data} />}
    </div>
  );
}
