"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Badge, Card, INPUT } from "@/components/ui";

type Config = {
  enabled: boolean;
  required: boolean;
  activeProfile: 1 | 2;
  baseUrl1: string;
  model1: string;
  baseUrl2: string;
  model2: string;
  prompt: string;
  timeout: number;
};

type TestResult = {
  ok: boolean;
  profile: 1 | 2;
  model: string;
  reply: string;
  image_attached: boolean;
  elapsed_ms: number;
  post_id?: number;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function initialConfig(initial: any): Config {
  return {
    enabled: !!initial?.ai_enabled,
    required: !!initial?.ai_required,
    activeProfile: Number(initial?.ai_active_profile) === 2 ? 2 : 1,
    baseUrl1: initial?.ai_base_url ?? "",
    model1: initial?.ai_model ?? "",
    baseUrl2: initial?.ai_secondary_base_url ?? "",
    model2: initial?.ai_secondary_model ?? "",
    prompt: initial?.ai_prompt ?? "",
    timeout: Number(initial?.ai_timeout ?? 40),
  };
}

function keyState(initial: any, secondary = false) {
  const key = secondary ? initial?.secondary_api_key : initial?.api_key;
  const configured = secondary ? initial?.secondary_api_key_configured : initial?.api_key_configured;
  return { configured: !!(configured ?? key?.configured), mask: key?.mask ?? "" };
}

async function waitForTest(actionId: string): Promise<TestResult> {
  for (let attempt = 0; attempt < 310; attempt += 1) {
    await sleep(1000);
    const response = await fetch(`/api/dash/actions/${actionId}`);
    if (!response.ok) continue;
    const action = await response.json();
    if (action.status === "completed") return action.result as TestResult;
    if (action.status === "failed") throw new Error(action.error || "Проверка завершилась с ошибкой");
  }
  throw new Error("Сервис не ответил за 5 минут. Проверьте журнал работы.");
}

export default function AiForm({ initial }: { initial: any }) {
  const [config, setConfig] = useState<Config>(() => initialConfig(initial));
  const [baseline, setBaseline] = useState<Config>(() => initialConfig(initial));
  const [keys, setKeys] = useState(() => ({ 1: keyState(initial), 2: keyState(initial, true) }));
  const [newKeys, setNewKeys] = useState({ 1: "", 2: "" });
  const [clearKeys, setClearKeys] = useState({ 1: false, 2: false });
  const [testText, setTestText] = useState("Сделай короткую и живую подпись к этому посту.");
  const [testPostId, setTestPostId] = useState("");
  const [testing, setTesting] = useState<1 | 2 | null>(null);
  const [testResults, setTestResults] = useState<Partial<Record<1 | 2, TestResult>>>({});
  const [testErrors, setTestErrors] = useState<Partial<Record<1 | 2, string>>>({});
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  const dirty = useMemo(
    () => JSON.stringify(config) !== JSON.stringify(baseline) || !!newKeys[1].trim() || !!newKeys[2].trim() || clearKeys[1] || clearKeys[2],
    [baseline, clearKeys, config, newKeys],
  );

  function update<K extends keyof Config>(key: K, value: Config[K]) {
    setConfig((current) => ({ ...current, [key]: value }));
    setMsg("");
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setMsg("");
    setErr("");
    if (config.baseUrl1 !== baseline.baseUrl1 && keys[1].configured && !newKeys[1].trim() && !clearKeys[1]) {
      setErr("Для нового адреса профиля 1 введите его API-ключ.");
      return;
    }
    if (config.baseUrl2 !== baseline.baseUrl2 && keys[2].configured && !newKeys[2].trim() && !clearKeys[2]) {
      setErr("Для нового адреса профиля 2 введите его API-ключ.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/dash/ai", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ai_enabled: config.enabled,
          ai_required: config.required,
          ai_active_profile: config.activeProfile,
          ai_base_url: config.baseUrl1,
          ai_model: config.model1,
          ai_secondary_base_url: config.baseUrl2,
          ai_secondary_model: config.model2,
          ai_prompt: config.prompt,
          ai_timeout: Number(config.timeout),
          ...(newKeys[1].trim() ? { api_key: newKeys[1] } : {}),
          ...(clearKeys[1] ? { clear_api_key: true } : {}),
          ...(newKeys[2].trim() ? { secondary_api_key: newKeys[2] } : {}),
          ...(clearKeys[2] ? { clear_secondary_api_key: true } : {}),
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.error || `Ошибка ${response.status}`);
      const saved = data?.settings ?? data;
      const nextConfig = saved?.ai_base_url !== undefined ? initialConfig(saved) : config;
      setBaseline(nextConfig);
      setConfig(nextConfig);
      setKeys({
        1: saved?.api_key || saved?.api_key_configured !== undefined ? keyState(saved) : { configured: clearKeys[1] ? false : keys[1].configured || !!newKeys[1].trim(), mask: saved?.api_key?.mask ?? (clearKeys[1] ? "" : keys[1].mask) },
        2: saved?.secondary_api_key || saved?.secondary_api_key_configured !== undefined ? keyState(saved, true) : { configured: clearKeys[2] ? false : keys[2].configured || !!newKeys[2].trim(), mask: saved?.secondary_api_key?.mask ?? (clearKeys[2] ? "" : keys[2].mask) },
      });
      setNewKeys({ 1: "", 2: "" });
      setClearKeys({ 1: false, 2: false });
      setMsg("Настройки сохранены. Тесты теперь используют эти значения.");
      router.refresh();
    } catch (error: any) {
      setErr(error?.message ?? "Не удалось сохранить настройки");
    } finally {
      setBusy(false);
    }
  }

  async function runTest(profile: 1 | 2) {
    if (dirty || testing) return;
    setTesting(profile);
    setTestErrors((current) => ({ ...current, [profile]: "" }));
    setTestResults((current) => ({ ...current, [profile]: undefined }));
    try {
      const postId = Number(testPostId);
      const response = await fetch("/api/dash/ai/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile, text: testText, ...(Number.isInteger(postId) && postId > 0 ? { post_id: postId } : {}) }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.error || `Ошибка ${response.status}`);
      if (!data?.action_id) throw new Error("Сервер не вернул номер проверки");
      const result = await waitForTest(data.action_id);
      if (!result?.ok) throw new Error("Сервис не подтвердил успешный ответ");
      setTestResults((current) => ({ ...current, [profile]: result }));
    } catch (error: any) {
      setTestErrors((current) => ({ ...current, [profile]: error?.message ?? "Проверка не удалась" }));
    } finally {
      setTesting(null);
    }
  }

  function profileCard(profile: 1 | 2) {
    const baseKey = profile === 1 ? "baseUrl1" : "baseUrl2";
    const modelKey = profile === 1 ? "model1" : "model2";
    const result = testResults[profile];
    const testError = testErrors[profile];
    return (
      <Card key={profile} title={`Профиль ${profile}`} description={profile === 1 ? "Основной AI-сервис." : "Второй независимый AI-сервис. Он не включается автоматически при ошибке первого."} className={config.activeProfile === profile ? "ring-1 ring-teal-400/40" : ""}>
        <div className="space-y-4">
          <label className="field-label">Адрес API<input type="url" value={config[baseKey]} onChange={(e) => update(baseKey, e.target.value)} placeholder="https://api.openai.com/v1" className={INPUT} /><span className="field-help">При смене адреса необходимо снова ввести ключ этого профиля.</span></label>
          <label className="field-label">Модель<input value={config[modelKey]} onChange={(e) => update(modelKey, e.target.value)} placeholder="gpt-4o-mini" className={INPUT} /></label>
          <label className="field-label">API-ключ<input type="password" autoComplete="new-password" value={newKeys[profile]} disabled={clearKeys[profile]} onChange={(e) => setNewKeys((current) => ({ ...current, [profile]: e.target.value }))} placeholder={keys[profile].configured ? "Оставьте пустым, чтобы сохранить текущий" : "Вставьте API-ключ"} className={INPUT} /></label>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className={keys[profile].configured ? "text-emerald-300" : "text-amber-300"}>{keys[profile].configured ? <>Ключ сохранён: <span className="font-mono">{keys[profile].mask || "••••"}</span></> : "Ключ не задан"}</span>
            {keys[profile].configured && <label className="flex cursor-pointer items-center gap-2 text-slate-400"><input type="checkbox" checked={clearKeys[profile]} onChange={(e) => { const checked = e.target.checked; setClearKeys((current) => ({ ...current, [profile]: checked })); if (checked) setNewKeys((current) => ({ ...current, [profile]: "" })); }} />Удалить сохранённый ключ</label>}
          </div>
          <div className="border-t border-slate-700/40 pt-4">
            <button type="button" onClick={() => runTest(profile)} disabled={dirty || testing !== null || !keys[profile].configured} className="button-secondary disabled:cursor-not-allowed disabled:opacity-50">{testing === profile ? "Ждём ответ сервиса…" : `Проверить профиль ${profile}`}</button>
            {dirty && <p className="mt-2 text-xs text-amber-300">Сначала сохраните изменения — тест всегда использует сохранённые настройки.</p>}
            {!dirty && !keys[profile].configured && <p className="mt-2 text-xs text-amber-300">Сначала добавьте и сохраните ключ.</p>}
            {testError && <div role="alert" className="mt-3 rounded-lg border border-red-500/25 bg-red-950/30 p-3 text-xs text-red-200">{testError}</div>}
            {result && <div role="status" className="mt-3 rounded-lg border border-emerald-500/25 bg-emerald-950/25 p-3 text-xs text-emerald-100"><div className="flex flex-wrap gap-2"><Badge v="completed">Профиль {result.profile}</Badge><span>{result.model}</span><span>{result.elapsed_ms} мс</span>{result.image_attached && <span>· изображение приложено</span>}</div><div className="mt-3 whitespace-pre-wrap leading-5 text-slate-200">{result.reply}</div></div>}
          </div>
        </div>
      </Card>
    );
  }

  return (
    <form onSubmit={save} className="space-y-5">
      <Card title="Общие настройки" description="Они действуют для обоих профилей.">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-700/50 bg-slate-950/25 p-4 text-sm text-slate-200"><input className="mt-0.5 accent-teal-500" type="checkbox" checked={config.enabled} onChange={(e) => update("enabled", e.target.checked)} /><span><b className="block">Использовать нейросеть</b><span className="mt-1 block text-xs leading-5 text-slate-400">Бот улучшает подпись перед публикацией.</span></span></label>
          <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-700/50 bg-slate-950/25 p-4 text-sm text-slate-200"><input className="mt-0.5 accent-teal-500" type="checkbox" checked={config.required} onChange={(e) => update("required", e.target.checked)} /><span><b className="block">Не публиковать при ошибке AI</b><span className="mt-1 block text-xs leading-5 text-slate-400">Защищает канал от публикации исходного текста, если AI не ответил.</span></span></label>
          <fieldset className="rounded-xl border border-slate-700/50 bg-slate-950/25 p-4 md:col-span-2"><legend className="px-1 text-xs font-semibold text-slate-300">Активный профиль</legend><div className="mt-1 flex flex-wrap gap-3">{([1, 2] as const).map((profile) => <label key={profile} className={`flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-3 text-sm ${config.activeProfile === profile ? "border-teal-400/40 bg-teal-500/10 text-teal-100" : "border-slate-700/50 text-slate-400"}`}><input type="radio" name="active-profile" checked={config.activeProfile === profile} onChange={() => update("activeProfile", profile)} />Профиль {profile}</label>)}</div><p className="mt-2 text-xs text-slate-500">Бот использует только выбранный профиль. Автоматического переключения между профилями нет.</p></fieldset>
          <label className="field-label">Максимальное время ответа, секунд<input type="number" min={5} max={300} value={config.timeout} onChange={(e) => update("timeout", Number(e.target.value))} className={INPUT} /><span className="field-help">От 5 до 300 секунд.</span></label>
          <label className="field-label md:col-span-2">Инструкция для нейросети<textarea rows={6} value={config.prompt} onChange={(e) => update("prompt", e.target.value)} className={INPUT} /><span className="field-help">Опишите стиль, длину и правила для новых подписей.</span></label>
        </div>
      </Card>

      <div className="grid gap-5 xl:grid-cols-2">{profileCard(1)}{profileCard(2)}</div>

      <Card title="Данные для проверки" description="Проверка ничего не публикует и не меняет активный профиль. Можно добавить номер поста, чтобы проверить распознавание реального изображения.">
        <div className="grid gap-4 md:grid-cols-[1fr_220px]">
          <label className="field-label">Пробный текст<input value={testText} onChange={(e) => setTestText(e.target.value)} className={INPUT} /></label>
          <label className="field-label">Номер поста с изображением <span className="field-help">Необязательно</span><input type="number" min={1} step={1} value={testPostId} onChange={(e) => setTestPostId(e.target.value)} placeholder="Например: 42" className={INPUT} /></label>
        </div>
      </Card>

      <div className="sticky bottom-3 z-20 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-700/60 bg-[#0b192b]/95 p-4 shadow-2xl shadow-black/30 backdrop-blur">
        <button disabled={busy || !dirty} className="button-primary disabled:cursor-not-allowed disabled:opacity-50">{busy ? "Сохраняем…" : dirty ? "Сохранить настройки" : "Изменения сохранены"}</button>
        {dirty && <span className="text-xs text-amber-300">Есть несохранённые изменения.</span>}
        {msg && <span role="status" className="text-xs text-emerald-300">{msg}</span>}
        {err && <span role="alert" className="text-xs text-red-300">{err}</span>}
      </div>
    </form>
  );
}
