import { NextRequest, NextResponse } from "next/server";
import { pubFetch } from "@/lib/api";

type Ctx = { params: { path: string[] } };

/** Белый список под-путей Control API, доступных панели. Метод зафиксирован. */
const ALLOWED: { method: string; re: RegExp }[] = [
  { method: "GET", re: /^overview$/ },
  { method: "GET", re: /^sources$/ },
  { method: "POST", re: /^sources$/ },
  { method: "PATCH", re: /^sources\/\d+$/ },
  { method: "DELETE", re: /^sources\/\d+$/ },
  { method: "POST", re: /^sources\/\d+\/(check|backfill)$/ },
  { method: "GET", re: /^posts$/ },
  { method: "GET", re: /^posts\/\d+$/ },
  { method: "POST", re: /^posts\/\d+\/(publish|requeue|skip|ai)$/ },
  { method: "GET", re: /^schedule$/ },
  { method: "PUT", re: /^schedule$/ },
  { method: "GET", re: /^settings$/ },
  { method: "PUT", re: /^settings$/ },
  { method: "GET", re: /^ai$/ },
  { method: "PUT", re: /^ai$/ },
  { method: "POST", re: /^ai\/test$/ },
  { method: "POST", re: /^own\/scan$/ },
  { method: "GET", re: /^own$/ },
  { method: "POST", re: /^own\/repost$/ },
  { method: "GET", re: /^actions$/ },
  { method: "GET", re: /^actions\/[\w-]+$/ },
  { method: "GET", re: /^events$/ },
];

async function handle(req: NextRequest, ctx: Ctx) {
  const sub = (ctx.params?.path ?? []).join("/");
  const method = req.method.toUpperCase();
  if (!ALLOWED.some((a) => a.method === method && a.re.test(sub))) {
    return NextResponse.json({ error: "not allowed" }, { status: 404 });
  }
  try {
    const init: RequestInit & { json?: unknown } = { method };
    if (!["GET", "HEAD"].includes(method)) {
      try {
        init.json = await req.json();
      } catch {
        init.json = {};
      }
    }
    const data = await pubFetch(`/api/${sub}${req.nextUrl.search}`, init);
    return NextResponse.json(data ?? {});
  } catch (e: any) {
    return NextResponse.json({ error: e?.message ?? "upstream error" }, { status: e?.status ?? 502 });
  }
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
