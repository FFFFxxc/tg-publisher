import { NextRequest, NextResponse } from "next/server";

/**
 * Опциональная basic-auth защита панели. Включается, если заданы
 * DASHBOARD_USERNAME и DASHBOARD_PASSWORD (иначе считаем, что панель закрыта иначе,
 * например платформенным auth провайдера деплоя).
 */
export function middleware(req: NextRequest) {
  const user = process.env.DASHBOARD_USERNAME;
  const password = process.env.DASHBOARD_PASSWORD;
  if (!user || !password) return NextResponse.next();
  const header = req.headers.get("authorization") ?? "";
  const expected = "Basic " + btoa(`${user}:${password}`);
  if (header === expected) return NextResponse.next();
  return new NextResponse("Требуется авторизация", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="tg-publisher dashboard"' },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
