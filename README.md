# tg-publisher: Telegram userbot publisher

Telethon (StringSession) + PostgreSQL-очередь + Docker + опциональные AI-подписи + SOCKS5 только для Telegram.
С версии 1.2: веб-панель управления (Control API + Next.js dashboard, см. `dashboard/README.md`).

## Как работает
1. **collect** (каждые `COLLECT_INTERVAL_SEC`): читает все включённые источники из `automation_sources`
   (`TG_INITIAL_SOURCE` только бутстрап), складывает посты как `candidate` вместе с метриками, обновляет
   просмотры/реакции/репосты/комменты у ещё живых кандидатов.
2. **Слоты** по `PUBLISH_TIMES` (или интервалу), тип слота по кругу из `SCHEDULE_PATTERN`, например
   `parsed,old,parsed,old`. Позиция в паттерне хранится в БД и переживает рестарт.
   - **parsed**: лучший кандидат старше `CANDIDATE_MIN_AGE_MIN` и моложе `MAX_POST_AGE_HOURS`. Score считается
     относительно среднего *своего* источника: `0.6·ER/avgER + 0.4·views/avgViews`,
     ER = (реакции + 3·репосты + 2·комменты)/просмотры. Ниже `BEST_MIN_SCORE` не публикуется.
     Если задан `AI_API_KEY`, AI получает текст + картинку (или превью видео) и пишет подпись. Если AI упал, идёт оригинал.
   - **old**: самый залайканный пост своего канала старше `OWN_MIN_AGE_DAYS`, который сам не репост и
     не повторялся `REPOST_COOLDOWN_DAYS`. Канал сканируется раз в `OWN_SCAN_HOURS`.
   - Нет подходящего поста нужного типа: берётся другой тип. Ретраи (`pending`) идут вне очереди.
3. **Подпись всегда** = текст + `👀 ХОТ КОНТЕНТ` / `😡 МЫ В МАКСЕ` с премиум-эмодзи (custom emoji entities,
   offset'ы в UTF-16) и ссылками. Если текст длинный, режется тело, а не подпись. У старых постов, где подпись
   уже есть, она не дублируется. Настраивается через `FOOTER_JSON`.
   **Аккаунту юзербота нужен Telegram Premium**, иначе эмодзи станут обычными. Проверить: `test-footer`.
4. **Защита от дублей** как раньше: `send_started_at`, затем сразу `dest_msg_ids`; обрыв во время отправки даёт `ambiguous`.
   Recovery на старте: `processing` с dest ids становится `published`, с `send_started` становится `ambiguous`, иначе `pending`.

Статусы: `candidate, pending, processing, published, failed, ambiguous, skipped, expired`.

## Деплой (VK Cloud)
```bash
cp .env.example .env && nano .env                 # api id/hash, канал, источники, пароль БД, AI-ключ
sudo cp deploy/socks-tunnel.service /etc/systemd/system/ && sudo systemctl enable --now socks-tunnel
docker compose up -d db
docker compose run --rm app login                 # один раз: номер, код из Telegram, 2FA
docker compose up -d --build
```
Сессия хранится в volume `appdata` и переживает рестарты/пересборки. Если её отозвать, бот не стартует
и попросит снова `login` (сам он в интерактив не полезет).
Вместо файла можно передать `TG_SESSION_STRING`, но это не обязательно.
Все остальные настройки (возраст кандидатов, кулдауны, лимиты) имеют дефолты в `app/config.py`, их можно переопределить в `.env`.

## Закрытые каналы
Источник или свой канал можно указать как `@name`, `-100ID` или инвайт `https://t.me/+xxxx`.
По инвайту бот сам вступит (если ещё не участник). Для `-100ID` аккаунт уже должен быть в канале.
Посты с запретом пересылки тоже работают: медиа скачивается и перезаливается, а не форвардится.

## Команды
```bash
docker compose exec app python -m app verify                 # auth, прокси в клиенте, БД, bootstrap + все DB-источники, канал
docker compose exec app python -m app add-source @channel
docker compose exec app python -m app test-media @src 12345  # скачать конкретное медиа (проверка FileMigrateError/другой DC)
docker compose exec app python -m app test-footer            # подпись с премиум-эмодзи в «Избранное»
docker compose exec app python -m app scan-own && docker compose exec app python -m app top-old
docker compose exec app python -m app requeue 42             # контролируемый ретрай ambiguous/failed
curl localhost:8080/health ; curl localhost:8080/ready
```

## Веб-панель (с версии 1.2)

Control API живёт в том же asyncio-процессе, что и worker, на отдельном порту:
- `CONTROL_API_PORT=8081`, `CONTROL_API_TOKEN=<длинный случайный>` — без токена API не стартует;
- каждый `/api/*` требует `Authorization: Bearer <CONTROL_API_TOKEN>`;
- тяжёлые операции — persistent actions в таблице `dashboard_actions`: воркер забирает их
  атомарно (`FOR UPDATE SKIP LOCKED`) и исполняет вне HTTP; зависшие/зависшие-при-рестарте
  actions помечаются failed, дубли публикации исключены (`send_started_at`/`dest_msg_ids`);
- события пишутся в таблицу `events` (страница «Активность»);
- runtime-настройки (таймзона, слоты, паттерн, пороги, пауза публикации, параметры AI, футер)
  хранятся в `kv` с префиксом `rt:` и применяются воркером на лету, без Docker restart;
  ENV остаётся бутстрапом/дефолтом;
- изоляция БД: все таблицы только в схеме `DB_SCHEMA` (по умолчанию `tg_publisher`),
  на старте проверяется `current_schema()` — при несовпадении воркер fail-fast, schema
  `public` старого `cross` не затрагивается;
- AI API key по-прежнему задаётся только через ENV (`AI_API_KEY`), через панель меняются
  остальные параметры и включение/выключение AI.

Dashboard — папка `dashboard/` (Next.js 14 + TS + Tailwind), деплой на Vercel, инструкция
по публикации Control API наружу — в `dashboard/README.md`.

## Приёмка (Definition of done)
- [x] unit-тесты: `python -m unittest discover -s tests -t .`
- [ ] `docker compose build`
- [ ] `verify`: transport socks5, client proxy set, все источники ok
- [ ] `test-media` на медиа из чужого DC
- [ ] `test-footer`: эмодзи премиумные, ссылки кликаются
- [ ] `top-old` показывает адекватный топ по реакциям
- [ ] реальный пост опубликован; `docker restart` -> дубля нет
- [ ] reboot сервера: туннель, Docker, Postgres, источники на месте
- [ ] `git status` без `.env`/сессий/ключей
