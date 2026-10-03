import "server-only";

const BASE = (process.env.PUBLISHER_API_URL ?? "").replace(/\/+$/, "");
const TOKEN = process.env.PUBLISHER_API_TOKEN ?? "";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function requestInit(init?: RequestInit & { json?: unknown }): RequestInit {
  const headers: Record<string, string> = { Authorization: `Bearer ${TOKEN}` };
  let body: string | undefined;
  if (init?.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  return { ...init, headers, body, cache: "no-store" };
}

/** Выполняет серверный запрос и возвращает исходный Response для бинарных маршрутов. */
export async function pubResponse(path: string, init?: RequestInit & { json?: unknown }): Promise<Response> {
  if (!BASE || !TOKEN) {
    throw new ApiError(500, "PUBLISHER_API_URL / PUBLISHER_API_TOKEN не заданы (см. dashboard/.env.example)");
  }
  return fetch(`${BASE}${path}`, requestInit(init));
}

/**
 * Серверный вызов Publisher Control API. Токен живёт только здесь:
 * браузер общается с Next.js route handler'ами, а не с Control API напрямую.
 */
export async function pubFetch<T = any>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const res = await pubResponse(path, init);
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    throw new ApiError(res.status, data?.error ?? `Control API ${res.status}`);
  }
  return data as T;
}
