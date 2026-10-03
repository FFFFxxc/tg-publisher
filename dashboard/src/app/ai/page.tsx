import { pubFetch } from "@/lib/api";
import { ErrorBox } from "@/components/ui";
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
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-zinc-100">AI-подписи</h1>
      {error ? <ErrorBox message={error} /> : <AiForm initial={data} />}
    </div>
  );
}
