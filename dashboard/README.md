# tg-publisher dashboard

Next.js 14 (App Router) + TypeScript + Tailwind. Тёмная русская админка для Control API воркера
`tg-publisher`. Деплоится на Vercel, **напрямую к PostgreSQL не подключается и не подключится**:
браузер → Next.js (server components + route handlers) → Publisher Control API (Bearer token).

Токен `PUBLISHER_API_TOKEN` существует только на сервере Next.js: клиентский бандл его не получает,
в браузер он не отдаётся ни в каком виде.

## Env (Vercel → Project → Settings → Environment Variables)

```env
PUBLISHER_API_URL=https://<адрес вашего Control API>
PUBLISHER_API_TOKEN=<тот же CONTROL_API_TOKEN, что в .env воркера>
# опционально, если панель не защищена иначе:
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=<пароль>
```

## Локальная проверка / production build

```bash
cd dashboard
npm install        # или npm ci при наличии package-lock.json
npm run build
```

Деплой на Vercel: import проекта, Root Directory = `dashboard`, добавить env выше.

## Как безопасно published Control API (8081) наружу

Воркер слушает `CONTROL_API_PORT` (по умолчанию 8081) на host network, т.е. на самом сервере.
Наружу его нужно выставлять только через TLS-прокси и желательно с ограничением по IP.

Вариант 1 — отдельный hostname (рекомендую): Caddy/nginx на сервере, отдельный поддомен,
проксирующий на `127.0.0.1:8081`, автоматический TLS:

```caddyfile # Caddyfile (новый site block; существующие блоки старого cross НЕ трогаем)
panel-api.example.com {
    reverse_proxy 127.0.0.1:8081
}
```

Вариант 2 — Tailscale Funnel/путь: отдельный hostname/path **только для нового API**.
Существующие Tailscale/Funnel endpoint'ы старого `cross` не меняются — при необходимости
добавьте отдельный блок, а не правьте старый.

Вариант 3 — не публиковать вообще: панель деплоится на Vercel, но `PUBLISHER_API_URL`
указывает на private hostname через Tailscale (если Vercel этого не умеет — используйте вариант 1).

Обязательные меры:
- `CONTROL_API_TOKEN` — длинный случайный (панель и воркер должны знать один и тот же);
- PostgreSQL наружу не публиковать (он и так слушает только 127.0.0.1 на сервере);
- не проксируйте на 8081 лишние пути — Control API сам отвечает только на `/api/*`;
- ответ API не содержит секретов: `AI_API_KEY`/`TG_*`/`DATABASE_URL` маскируются или не отдаются.

## Структура

- `src/lib/api.ts` — серверный клиент Control API (token не покидает сервер);
- `src/app/api/dash/[...path]/route.ts` — прокси с жёстким allowlist путей/методов;
- `src/middleware.ts` — опциональная basic-auth на панель;
- страницы: Обзор, Публикации (+детали поста), Источники, Расписание, Нейросеть,
  Подпись к постам, Архив канала и История действий. Интерфейс адаптирован для телефона.
- В разделе «Нейросеть» доступны модель, адрес API и замена/удаление API-ключа без
  перезапуска бота. Пустое поле ключа сохраняет его; сохранённый ключ отображается маской.

Все «тяжёлые» действия (добавить источник, backfill, publish now, ретрай, AI, скан, репост) —
persistent actions: панель только создаёт запись, воркер исполняет и отчитывается статусом.
Кнопки в UI дожидается реального backend-статуса, а не рисуют «готово».
