"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { INPUT } from "@/components/ui";

type Step = "phone" | "code" | "password";

export default function ActivityLoginForm() {
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [phoneMask, setPhoneMask] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const router = useRouter();

  async function request(path: string, body: unknown) {
    const response = await fetch(`/api/dash/${path}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data?.error || `ошибка ${response.status}`);
    return data;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      if (step === "phone") {
        const data = await request("activity-accounts/login/start", { phone });
        setToken(data.login_token); setPhoneMask(data.phone_mask); setStep("code");
        setMessage("Код отправлен в Telegram");
      } else {
        const data = await request("activity-accounts/login/complete", {
          login_token: token, code: step === "code" ? code : "", password: step === "password" ? password : "",
        });
        if (data.password_required) {
          setStep("password"); setMessage("Введите пароль двухэтапной аутентификации");
        } else {
          setMessage(`Аккаунт ${data.display_name} подключён`);
          setStep("phone"); setPhone(""); setCode(""); setPassword(""); setToken("");
          router.refresh();
        }
      }
    } catch (e: any) {
      setError(e?.message ?? "Не удалось выполнить вход");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[minmax(260px,1fr)_auto]">
      {step === "phone" && <label className="field-label">Номер телефона
        <input autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)}
          placeholder="+79991234567" className={`w-full ${INPUT}`} />
      </label>}
      {step === "code" && <label className="field-label">Код для {phoneMask}
        <input autoComplete="one-time-code" inputMode="numeric" value={code}
          onChange={(e) => setCode(e.target.value)} placeholder="Код из Telegram"
          className={`w-full ${INPUT}`} />
      </label>}
      {step === "password" && <label className="field-label">Пароль 2FA для {phoneMask}
        <input autoComplete="current-password" type="password" value={password}
          onChange={(e) => setPassword(e.target.value)} placeholder="Облачный пароль Telegram"
          className={`w-full ${INPUT}`} />
      </label>}
      <div className="flex items-end gap-2">
        <button disabled={busy} className="button-primary disabled:opacity-50">
          {busy ? "Подключение…" : step === "phone" ? "Получить код" : step === "code" ? "Подтвердить код" : "Подтвердить пароль"}
        </button>
        {step !== "phone" && <button type="button" className="button-secondary" onClick={() => { setStep("phone"); setToken(""); setError(""); }}>Назад</button>}
      </div>
      {(message || error) && <div role="status" className={`sm:col-span-2 text-xs ${error ? "text-red-300" : "text-emerald-300"}`}>{error || message}</div>}
      <span className="field-help sm:col-span-2">Номер и код используются только во время входа. После авторизации сохраняется отдельная Telethon-сессия в закрытом томе приложения.</span>
    </form>
  );
}
