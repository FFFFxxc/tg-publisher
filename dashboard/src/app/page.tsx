import Overview from "@/components/Overview";
import { ErrorBox } from "@/components/ui";
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
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-zinc-100">Обзор</h1>
      {error ? <ErrorBox message={error} /> : <Overview initial={data} />}
    </div>
  );
}
