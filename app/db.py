"""PostgreSQL-очередь на psycopg 3. Схема идемпотентна, ничего не удаляет.
Всё живёт в изолированной схеме (по умолчанию tg_publisher): schema public старого
cross не трогается, при старте проверяется current_schema() и воркер fail-fast-ится."""
from __future__ import annotations

import json
import logging
import re
import uuid

from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .logic import Post, recovery_action, PENDING, AI_NOT_NEEDED, AI_UNCHECKED

log = logging.getLogger("db")

SCHEMA_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class SchemaIsolationError(RuntimeError):
    pass


def assert_current_schema(actual: str | None, expected: str):
    """Чистая проверка изоляции схемы: не та схема — не запускаемся."""
    if actual != expected:
        raise SchemaIsolationError(
            f"current_schema()={actual!r}, expected {expected!r}. "
            "Проверь DATABASE_URL/DB_SCHEMA: проект обязан работать только в своей схеме, "
            "чтобы не задеть таблицы старого cross в public.")


SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_sources (
    id BIGSERIAL PRIMARY KEY,
    ref TEXT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_message_id BIGINT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE automation_sources ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'source';
ALTER TABLE automation_sources ADD COLUMN IF NOT EXISTS title TEXT;

CREATE TABLE IF NOT EXISTS posts (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES automation_sources(id),
    group_key TEXT NOT NULL,
    source_msg_ids BIGINT[] NOT NULL,
    source_date TIMESTAMPTZ NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'candidate',
    ai_status TEXT NOT NULL DEFAULT 'unchecked',
    ai_caption TEXT,
    ai_error TEXT,
    dest_msg_ids BIGINT[] NOT NULL DEFAULT '{}',
    send_started_at TIMESTAMPTZ,
    attempts INT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    last_error TEXT,
    claimed_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, group_key)
);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'parsed';
ALTER TABLE posts ADD COLUMN IF NOT EXISTS views INT NOT NULL DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS reactions INT NOT NULL DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS forwards INT NOT NULL DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS replies INT NOT NULL DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS score DOUBLE PRECISION;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS media_type TEXT NOT NULL DEFAULT 'unknown';
CREATE INDEX IF NOT EXISTS posts_scheduled_idx ON posts (scheduled_at) WHERE scheduled_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS posts_status_idx ON posts (status, next_attempt_at);

-- снимок собственного канала для репостов «старых залайканных»
CREATE TABLE IF NOT EXISTS own_posts (
    group_key TEXT PRIMARY KEY,
    msg_ids BIGINT[] NOT NULL,
    post_date TIMESTAMPTZ NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    reactions INT NOT NULL DEFAULT 0,
    views INT NOT NULL DEFAULT 0,
    forwards INT NOT NULL DEFAULT 0,
    last_reposted_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS promo_runs (
    slot TEXT PRIMARY KEY,
    source_ref TEXT NOT NULL,
    group_key TEXT,
    source_msg_ids BIGINT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'sending',
    dest_msg_ids BIGINT[] NOT NULL DEFAULT '{}',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_ref, group_key)
);
CREATE TABLE IF NOT EXISTS weekly_runs (
    slot TEXT PRIMARY KEY,
    source_ref TEXT NOT NULL,
    group_key TEXT,
    source_msg_ids BIGINT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'preparing',
    dest_msg_ids BIGINT[] NOT NULL DEFAULT '{}',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_ref, group_key)
);
ALTER TABLE weekly_runs ADD COLUMN IF NOT EXISTS send_started_at TIMESTAMPTZ;
ALTER TABLE own_posts ADD COLUMN IF NOT EXISTS media_type TEXT NOT NULL DEFAULT 'unknown';

-- постоянные действия панели (исполняются воркером, не HTTP-запросом)
CREATE TABLE IF NOT EXISTS dashboard_actions (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending',
    post_id BIGINT,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS dashboard_actions_status_idx ON dashboard_actions (status, created_at);

-- структурированные события для страницы «Активность»
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    type TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    post_id BIGINT,
    source_id BIGINT,
    action_id TEXT,
    message TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS events_created_idx ON events (created_at DESC);
CREATE INDEX IF NOT EXISTS events_post_idx ON events (post_id);

-- Дополнительные пользовательские аккаунты, которые ставят реакцию на новые
-- публикации собственного канала. Файлы Telethon-сессий лежат в appdata;
-- база хранит только путь и безопасные метаданные для панели.
CREATE TABLE IF NOT EXISTS activity_accounts (
    id TEXT PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL UNIQUE,
    phone_mask TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    session_path TEXT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    status TEXT NOT NULL DEFAULT 'ready',
    last_error TEXT,
    last_active_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS activity_reactions (
    account_id TEXT NOT NULL REFERENCES activity_accounts(id) ON DELETE CASCADE,
    target_ref TEXT NOT NULL DEFAULT '',
    message_id BIGINT NOT NULL,
    reacted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, target_ref, message_id)
);
ALTER TABLE activity_reactions ADD COLUMN IF NOT EXISTS target_ref TEXT NOT NULL DEFAULT '';
ALTER TABLE activity_reactions DROP CONSTRAINT IF EXISTS activity_reactions_pkey;
ALTER TABLE activity_reactions ADD PRIMARY KEY (account_id, target_ref, message_id);
CREATE INDEX IF NOT EXISTS activity_reactions_message_idx ON activity_reactions (message_id);
"""

RET = """p.id, p.kind, p.source_id, s.ref AS source_ref, p.source_msg_ids, p.text,
         p.ai_status, p.ai_caption, p.attempts"""

POST_STATUSES = ("candidate", "pending", "processing", "published", "failed", "ambiguous", "skipped", "expired")


def build_posts_where(f: dict) -> tuple[str, list]:
    """Чистый сборщик WHERE для списка постов: только параметризованные условия."""
    conds, args = ["TRUE"], []
    if f.get("status"):
        conds.append("p.status = %s")
        args.append(f["status"])
    if f.get("kind"):
        conds.append("p.kind = %s")
        args.append(f["kind"])
    if f.get("media_type"):
        conds.append("p.media_type = %s")
        args.append(f["media_type"])
    if f.get("ai_status"):
        conds.append("p.ai_status = %s")
        args.append(f["ai_status"])
    if f.get("source_id"):
        conds.append("p.source_id = %s")
        args.append(int(f["source_id"]))
    if f.get("date_from"):
        conds.append("p.source_date >= %s")
        args.append(f["date_from"])
    if f.get("date_to"):
        conds.append("p.source_date < %s")
        args.append(f["date_to"])
    if f.get("q"):
        q = str(f["q"])
        if q.lstrip("-").isdigit():
            conds.append("(p.text ILIKE %s OR p.id::text = %s)")
            args.extend([f"%{q}%", q])
        else:
            conds.append("p.text ILIKE %s")
            args.append(f"%{q}%")
    return " AND ".join(conds), args


def build_events_where(f: dict) -> tuple[str, list]:
    conds, args = ["TRUE"], []
    if f.get("type"):
        conds.append("type = %s")
        args.append(f["type"])
    if f.get("level"):
        conds.append("level = %s")
        args.append(f["level"])
    if f.get("post_id"):
        conds.append("post_id = %s")
        args.append(int(f["post_id"]))
    if f.get("source_id"):
        conds.append("source_id = %s")
        args.append(int(f["source_id"]))
    if f.get("action_id"):
        conds.append("action_id = %s")
        args.append(f["action_id"])
    return " AND ".join(conds), args


class DB:
    def __init__(self, dsn: str, schema: str = "tg_publisher"):
        if not SCHEMA_NAME_RE.fullmatch(schema or ""):
            raise SchemaIsolationError(f"bad DB_SCHEMA name: {schema!r}")
        self.schema = schema
        self.pool = AsyncConnectionPool(dsn, min_size=1, max_size=5, open=False,
                                        kwargs={"row_factory": dict_row, "autocommit": True,
                                                "options": f"-c search_path={schema}"})

    async def open(self):
        await self.pool.open(wait=True, timeout=30)
        async with self.pool.connection() as c:
            await c.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            await c.execute(f"SET search_path = {self.schema}")
            cur = await c.execute("SELECT current_schema() AS s")
            row = await cur.fetchone()
            assert_current_schema(row["s"], self.schema)
            await c.execute(SCHEMA)
        log.info("db ready, schema=%s ensured (isolation checked)", self.schema)

    async def close(self):
        await self.pool.close()

    async def ping(self) -> bool:
        try:
            async with self.pool.connection(timeout=5) as c:
                await c.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def activity_accounts(self) -> list[dict]:
        return await self._q(
            "SELECT id, telegram_user_id, phone_mask, display_name, session_path, enabled, status, "
            "last_error, last_active_at, created_at, updated_at FROM activity_accounts "
            "ORDER BY created_at"
        )

    async def activity_account(self, account_id: str) -> dict | None:
        rows = await self._q("SELECT * FROM activity_accounts WHERE id=%s", (account_id,))
        return rows[0] if rows else None

    async def activity_account_by_telegram_id(self, telegram_user_id: int) -> dict | None:
        rows = await self._q("SELECT * FROM activity_accounts WHERE telegram_user_id=%s",
                             (telegram_user_id,))
        return rows[0] if rows else None

    async def save_activity_account(self, account_id: str, telegram_user_id: int,
                                    phone_mask: str, display_name: str, session_path: str) -> str:
        rows = await self._q(
            "INSERT INTO activity_accounts "
            "(id, telegram_user_id, phone_mask, display_name, session_path, enabled, status, last_error) "
            "VALUES (%s,%s,%s,%s,%s,TRUE,'ready',NULL) "
            "ON CONFLICT (telegram_user_id) DO UPDATE SET phone_mask=EXCLUDED.phone_mask, "
            "display_name=EXCLUDED.display_name, session_path=EXCLUDED.session_path, enabled=TRUE, "
            "status='ready', last_error=NULL, updated_at=now() RETURNING id",
            (account_id, telegram_user_id, phone_mask, display_name, session_path),
        )
        return rows[0]["id"]

    async def set_activity_account_enabled(self, account_id: str, enabled: bool) -> bool:
        rows = await self._q(
            "UPDATE activity_accounts SET enabled=%s, updated_at=now() WHERE id=%s RETURNING id",
            (enabled, account_id),
        )
        return bool(rows)

    async def set_activity_account_status(self, account_id: str, status: str,
                                          error: str | None = None) -> None:
        await self._q(
            "UPDATE activity_accounts SET status=%s, last_error=%s, "
            "last_active_at=CASE WHEN %s='ready' THEN now() ELSE last_active_at END, "
            "updated_at=now() WHERE id=%s",
            (status, error, status, account_id),
        )

    async def delete_activity_account(self, account_id: str) -> dict | None:
        rows = await self._q("DELETE FROM activity_accounts WHERE id=%s RETURNING session_path",
                             (account_id,))
        return rows[0] if rows else None

    async def activity_reacted(self, account_id: str, target_ref: str, message_id: int) -> bool:
        return bool(await self._q(
            "SELECT 1 FROM activity_reactions WHERE account_id=%s AND target_ref=%s AND message_id=%s",
            (account_id, target_ref, message_id),
        ))

    async def mark_activity_reacted(self, account_id: str, target_ref: str, message_id: int) -> None:
        await self._q(
            "INSERT INTO activity_reactions(account_id,target_ref,message_id) VALUES (%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            (account_id, target_ref, message_id),
        )

    async def _q(self, sql, args=()):
        async with self.pool.connection() as c:
            cur = await c.execute(sql, args)
            return await cur.fetchall() if cur.description else []

    # --- kv ---
    async def kv_get(self, k, default=None):
        r = await self._q("SELECT v FROM kv WHERE k=%s", (k,))
        return r[0]["v"] if r else default

    async def promo_has_slot(self, slot):
        return bool(await self._q('SELECT 1 FROM promo_runs WHERE slot=%s', (slot,)))

    async def promo_used(self, ref):
        rows = await self._q('SELECT group_key FROM promo_runs WHERE source_ref=%s AND group_key IS NOT NULL', (ref,))
        return {r['group_key'] for r in rows}

    async def promo_claim(self, slot, ref, group_key, ids):
        return bool(await self._q(
            'INSERT INTO promo_runs(slot,source_ref,group_key,source_msg_ids) SELECT %s,%s,%s,%s '
            "WHERE COALESCE((SELECT v::double precision FROM kv WHERE k='promo_retry_after'),0) "
            '<= EXTRACT(EPOCH FROM now()) '
            'ON CONFLICT DO NOTHING RETURNING slot', (slot, ref, group_key, ids)))

    async def promo_finish(self, slot, status, ids=(), error=None):
        await self._q('UPDATE promo_runs SET status=%s,dest_msg_ids=%s,error=%s,updated_at=now() WHERE slot=%s',
                      (status, list(ids), error, slot))

    async def promo_defer(self, slot, retry_after):
        await self._q("WITH cooldown AS (INSERT INTO kv(k,v) VALUES ('promo_retry_after',%s) "
                      "ON CONFLICT(k) DO UPDATE SET v=EXCLUDED.v RETURNING k) "
                      "DELETE FROM promo_runs WHERE slot=%s AND status='sending' "
                      "AND EXISTS(SELECT 1 FROM cooldown)", (str(retry_after), slot))

    async def weekly_recover(self):
        await self._q("DELETE FROM weekly_runs WHERE status='preparing' AND send_started_at IS NULL "
                      "AND cardinality(dest_msg_ids)=0 AND updated_at < now()-interval '20 minutes'")
        await self._q("UPDATE weekly_runs SET status='ambiguous',error='Interrupted after send boundary',updated_at=now() "
                      "WHERE status='sending' AND updated_at < now()-interval '20 minutes'")

    async def weekly_start_send(self, slot):
        return bool(await self._q("UPDATE weekly_runs SET status='sending',send_started_at=now(),updated_at=now() "
                                  "WHERE slot=%s AND status='preparing' RETURNING slot", (slot,)))

    async def weekly_has_slot(self, slot):
        return bool(await self._q('SELECT 1 FROM weekly_runs WHERE slot=%s', (slot,)))

    async def weekly_used(self, ref):
        rows = await self._q('SELECT group_key FROM weekly_runs WHERE source_ref=%s AND group_key IS NOT NULL', (ref,))
        return {r['group_key'] for r in rows}

    async def weekly_claim(self, slot, ref, group_key, ids):
        return bool(await self._q(
            "INSERT INTO weekly_runs(slot,source_ref,group_key,source_msg_ids,status) SELECT %s,%s,%s,%s,'preparing' "
            "WHERE COALESCE((SELECT v::double precision FROM kv WHERE k='weekly_retry_after'),0) "
            '<= EXTRACT(EPOCH FROM now()) '
            'ON CONFLICT DO NOTHING RETURNING slot', (slot, ref, group_key, ids)))

    async def weekly_finish(self, slot, status, ids=(), error=None):
        await self._q('UPDATE weekly_runs SET status=%s,dest_msg_ids=%s,error=%s,updated_at=now() WHERE slot=%s',
                      (status, list(ids), error, slot))

    async def weekly_defer(self, slot, retry_after):
        await self._q("WITH cooldown AS (INSERT INTO kv(k,v) VALUES ('weekly_retry_after',%s) "
                      "ON CONFLICT(k) DO UPDATE SET v=EXCLUDED.v RETURNING k) "
                      "DELETE FROM weekly_runs WHERE slot=%s AND status IN ('preparing','sending') AND cardinality(dest_msg_ids)=0 "
                      "AND EXISTS(SELECT 1 FROM cooldown)", (str(retry_after), slot))

    async def kv_set(self, k, v):
        await self._q("INSERT INTO kv VALUES (%s,%s) ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v", (k, str(v)))

    async def kv_prefix(self, prefix: str) -> dict:
        rows = await self._q("SELECT k, v FROM kv WHERE k LIKE %s", (prefix + "%",))
        return {r["k"][len(prefix):]: r["v"] for r in rows}

    # --- источники ---
    async def ensure_source(self, ref: str, role: str = "source") -> int | None:
        if not ref:
            return None
        r = await self._q("INSERT INTO automation_sources(ref, role) VALUES (%s,%s) "
                          "ON CONFLICT (ref) DO UPDATE SET ref=EXCLUDED.ref RETURNING id", (ref, role))
        return r[0]["id"]

    async def sources(self, only_enabled=True):
        sql = "SELECT * FROM automation_sources WHERE role='source'" + (" AND enabled" if only_enabled else "") + " ORDER BY id"
        return await self._q(sql)

    async def get_source(self, sid: int):
        rows = await self._q("SELECT * FROM automation_sources WHERE id=%s AND role='source'", (sid,))
        return rows[0] if rows else None

    async def enabled_sources_count(self) -> int:
        rows = await self._q("SELECT count(*) AS n FROM automation_sources WHERE role='source' AND enabled")
        return rows[0]["n"]

    async def add_source_checked(self, ref: str, title: str | None) -> tuple[int | None, bool]:
        """Дубль не создаём: ON CONFLICT DO NOTHING, (id, created)."""
        rows = await self._q("INSERT INTO automation_sources(ref, role, title) VALUES (%s,'source',%s) "
                             "ON CONFLICT (ref) DO NOTHING RETURNING id", (ref, title))
        if rows:
            return rows[0]["id"], True
        rows = await self._q("SELECT id FROM automation_sources WHERE ref=%s", (ref,))
        return (rows[0]["id"] if rows else None), False

    async def set_source_cursor(self, sid: int, last_id: int | None, error: str | None = None):
        await self._q("UPDATE automation_sources SET last_message_id=COALESCE(%s,last_message_id), "
                      "last_error=%s, updated_at=now() WHERE id=%s", (last_id, error, sid))

    async def set_source_title(self, sid: int, title: str | None):
        await self._q("UPDATE automation_sources SET title=COALESCE(%s,title), updated_at=now() WHERE id=%s",
                      (title, sid))

    async def set_source_enabled(self, sid: int, enabled: bool) -> bool:
        rows = await self._q("UPDATE automation_sources SET enabled=%s, updated_at=now() "
                             "WHERE id=%s AND role='source' RETURNING id", (enabled, sid))
        return bool(rows)

    async def delete_source(self, sid: int) -> str:
        """Hard delete только без FK-конфликтов; иначе вызывающий выключит источник."""
        try:
            rows = await self._q("DELETE FROM automation_sources WHERE id=%s AND role='source' RETURNING id", (sid,))
        except pg_errors.ForeignKeyViolation:
            return "has_posts"
        return "deleted" if rows else "missing"

    # --- кандидаты из источников ---
    async def upsert_candidate(self, sid, key, ids, date, text, stats: dict, ai_enabled: bool):
        ai = AI_UNCHECKED if ai_enabled else AI_NOT_NEEDED
        await self._q("""
            INSERT INTO posts(source_id, group_key, source_msg_ids, source_date, text, ai_status, status,
                              views, reactions, forwards, replies, media_type)
            VALUES (%s,%s,%s,%s,%s,%s,'candidate',%s,%s,%s,%s,%s)
            ON CONFLICT (source_id, group_key) DO UPDATE SET
              source_msg_ids = (SELECT array_agg(DISTINCT x ORDER BY x)
                                FROM unnest(posts.source_msg_ids || EXCLUDED.source_msg_ids) x),
              text = CASE WHEN posts.text = '' THEN EXCLUDED.text ELSE posts.text END,
              media_type = EXCLUDED.media_type,
              updated_at = now()
            WHERE posts.status = 'candidate'
        """, (sid, key, ids, date, text, ai, stats["views"], stats["reactions"], stats["forwards"], stats["replies"], stats.get('media_type', 'unknown')))

    async def backfill_candidates(self, sid, items: list[tuple], ai_enabled: bool) -> int:
        """Backfill конкретного источника: только новые candidate, курсор не трогаем, дубли исключены."""
        ai = AI_UNCHECKED if ai_enabled else AI_NOT_NEEDED
        n = 0
        for key, ids, date, text, st in items:
            rows = await self._q("""
                INSERT INTO posts(source_id, group_key, source_msg_ids, source_date, text, ai_status, status,
                                  views, reactions, forwards, replies, media_type)
                VALUES (%s,%s,%s,%s,%s,%s,'candidate',%s,%s,%s,%s,%s)
                ON CONFLICT (source_id, group_key) DO NOTHING RETURNING id""",
                (sid, key, ids, date, text, ai, st["views"], st["reactions"], st["forwards"], st["replies"], st.get('media_type', 'unknown')))
            n += len(rows)
        return n

    async def candidates_for_refresh(self, max_age_h: int):
        return await self._q("""SELECT p.id, s.ref, p.source_msg_ids FROM posts p
            JOIN automation_sources s ON s.id=p.source_id
            WHERE p.status='candidate' AND p.kind='parsed'
              AND p.source_date >= now() - make_interval(hours => %s)""", (max_age_h,))

    async def set_stats(self, pid, st: dict):
        await self._q("UPDATE posts SET views=%s, reactions=%s, forwards=%s, replies=%s, media_type=%s, updated_at=now() WHERE id=%s",
                      (st["views"], st["reactions"], st["forwards"], st["replies"], st.get('media_type', 'unknown'), pid))

    async def unclassified_posts(self):
        return await self._q("SELECT p.id, p.source_msg_ids, s.ref FROM posts p JOIN automation_sources s ON s.id=p.source_id WHERE p.media_type='unknown' ORDER BY p.id DESC LIMIT 100")

    async def set_media_type(self, pid, media):
        await self._q('UPDATE posts SET media_type=%s WHERE id=%s', (media, pid))

    async def claim_best_candidate(self, min_age_min, max_age_h, baseline_days, min_score) -> Post | None:
        """Лучший кандидат относительно средних показателей СВОЕГО источника:
        score = 0.6 * ER/avgER + 0.4 * views/avgViews, ER = (реакции + 3*репосты + 2*комменты)/просмотры."""
        rows = await self._q(f"""
            WITH base AS (
              SELECT id, source_id, status, source_date, scheduled_at, views,
                     (reactions + 3*forwards + 2*replies)::float / GREATEST(views,1) AS er
              FROM posts WHERE kind='parsed'
                AND source_date >= now() - make_interval(days => %s)
            ), norm AS (
              SELECT id, status, source_date, scheduled_at,
                     COALESCE(0.6 * er / NULLIF(avg(er) OVER w, 0), 0.6)
                   + COALESCE(0.4 * views / NULLIF(avg(views) OVER w, 0), 0.4) AS score
              FROM base WINDOW w AS (PARTITION BY source_id)
            ), best AS (
              SELECT id, score FROM norm
              WHERE status='candidate' AND scheduled_at IS NULL
                AND source_date <= now() - make_interval(mins => %s)
                AND source_date >= now() - make_interval(hours => %s)
                AND score >= %s
              ORDER BY score DESC LIMIT 1
            )
            UPDATE posts p SET status='processing', claimed_at=now(), attempts=attempts+1,
                               score=best.score, updated_at=now()
            FROM best, automation_sources s
            WHERE p.id=best.id AND p.status='candidate' AND p.scheduled_at IS NULL AND s.id=p.source_id
            RETURNING {RET}, best.score AS _score""",
            (baseline_days, min_age_min, max_age_h, min_score))
        if not rows:
            return None
        r = rows[0]
        log.info("best candidate post=%s score=%.2f", r["id"], r.pop("_score"))
        return Post(**r)

    # --- собственный канал ---
    async def upsert_own(self, key, ids, date, text, reactions, views, forwards, media_type='unknown'):
        await self._q("""INSERT INTO own_posts(group_key, msg_ids, post_date, text, reactions, views, forwards, media_type)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (group_key) DO UPDATE SET msg_ids=EXCLUDED.msg_ids, text=EXCLUDED.text,
              reactions=EXCLUDED.reactions, views=EXCLUDED.views, forwards=EXCLUDED.forwards, media_type=EXCLUDED.media_type, updated_at=now()""",
            (key, ids, date, text, reactions, views, forwards, media_type))

    async def claim_best_own(self, own_sid, min_age_days, cooldown_days) -> Post | None:
        """Самый залайканный старый пост своего канала, который сам не является репостом
        и не репостился в течение cooldown."""
        rows = await self._q("""
            WITH best AS (
              SELECT o.group_key, o.msg_ids, o.post_date, o.text, o.reactions, o.media_type FROM own_posts o
              WHERE o.post_date <= now() - make_interval(days => %s)
                AND (o.last_reposted_at IS NULL OR o.last_reposted_at <= now() - make_interval(days => %s))
                AND NOT EXISTS (SELECT 1 FROM posts r WHERE r.kind='repost' AND r.dest_msg_ids && o.msg_ids)
                AND NOT EXISTS (SELECT 1 FROM posts r WHERE r.kind='repost' AND r.source_msg_ids = o.msg_ids
                                AND r.status IN ('candidate','processing','pending','ambiguous'))
              ORDER BY o.reactions DESC, o.forwards DESC LIMIT 1
              FOR UPDATE SKIP LOCKED
            ), mark AS (
              UPDATE own_posts o SET last_reposted_at=now() FROM best WHERE o.group_key=best.group_key
            )
            INSERT INTO posts(source_id, kind, group_key, source_msg_ids, source_date, text, status,
                              ai_status, attempts, claimed_at, reactions, media_type)
            SELECT %s, 'repost', 'r' || best.group_key || ':' || extract(epoch FROM now())::bigint,
                   best.msg_ids, best.post_date, best.text, 'processing', 'not_needed', 1, now(), best.reactions, best.media_type
            FROM best RETURNING id""", (min_age_days, cooldown_days, own_sid))
        if not rows:
            return None
        return await self._load(rows[0]["id"])

    async def own_page(self, order: str = "reactions", limit: int = 50, offset: int = 0, media_type='') -> tuple[list, int]:
        ob = "reactions DESC, forwards DESC" if order == "reactions" else "post_date DESC"
        where = ' WHERE media_type=%s' if media_type else ''
        args = (media_type,) if media_type else ()
        total = (await self._q('SELECT count(*) AS n FROM own_posts' + where, args))[0]["n"]
        rows = await self._q(f"SELECT * FROM own_posts{where} ORDER BY {ob} LIMIT %s OFFSET %s", (*args, limit, offset))
        return rows, total

    async def get_own(self, group_key: str):
        rows = await self._q("SELECT * FROM own_posts WHERE group_key=%s", (group_key,))
        return rows[0] if rows else None

    async def own_count(self) -> int:
        return (await self._q("SELECT count(*) AS n FROM own_posts"))[0]["n"]

    async def mark_own_reposted(self, group_key: str):
        await self._q("UPDATE own_posts SET last_reposted_at=now(), updated_at=now() WHERE group_key=%s",
                      (group_key,))

    async def create_repost_from_own(self, own_sid, group_key: str, ids, date, text, reactions, scheduled_at=None) -> int | None:
        """Ручной репост своего поста через обычный publish pipeline. Защита от дублей:
        не создаём пост, если этот контент уже ушёл в канал или уже в очереди на отправку."""
        rows = await self._q("""
            INSERT INTO posts(source_id, kind, group_key, source_msg_ids, source_date, text, status,
                              ai_status, attempts, reactions, scheduled_at, media_type)
            SELECT %s,'repost',%s,%s,%s,%s,'candidate','not_needed',1,%s,%s,
                   COALESCE((SELECT media_type FROM own_posts WHERE group_key=%s), 'unknown')
            WHERE NOT EXISTS (SELECT 1 FROM posts r WHERE r.kind='repost' AND r.dest_msg_ids && %s::bigint[])
              AND NOT EXISTS (SELECT 1 FROM posts r WHERE r.kind='repost' AND r.source_msg_ids = %s::bigint[]
                              AND r.status IN ('candidate','processing','pending','ambiguous'))
            RETURNING id""",
            (own_sid, f"r{group_key}:{uuid.uuid4().hex[:8]}", ids, date, text, reactions, scheduled_at, group_key, ids, ids))
        return rows[0]["id"] if rows else None

    # --- очередь: списки для панели ---
    async def posts_page(self, filters: dict, limit: int, offset: int) -> tuple[list, int]:
        where, args = build_posts_where(filters or {})
        total = (await self._q(f"SELECT count(*) AS n FROM posts p WHERE {where}", args))[0]["n"]
        rows = await self._q(f"""SELECT p.*, s.ref AS source_ref, s.title AS source_title
            FROM posts p JOIN automation_sources s ON s.id=p.source_id
            WHERE {where} ORDER BY p.id DESC LIMIT %s OFFSET %s""", args + [limit, offset])
        return rows, total

    async def get_post(self, pid: int):
        rows = await self._q("""SELECT p.*, s.ref AS source_ref, s.title AS source_title
            FROM posts p JOIN automation_sources s ON s.id=p.source_id WHERE p.id=%s""", (pid,))
        return rows[0] if rows else None

    async def counts_by_status(self) -> dict:
        rows = await self._q("SELECT status, count(*) AS n FROM posts GROUP BY status")
        return {r["status"]: r["n"] for r in rows}

    async def published_stats(self, today_start) -> dict:
        rows = await self._q("""SELECT count(*) FILTER (WHERE published_at >= %s) AS today,
            count(*) FILTER (WHERE published_at >= now() - interval '24 hours') AS h24
            FROM posts WHERE status='published'""", (today_start,))
        return {"today": rows[0]["today"], "h24": rows[0]["h24"]}

    async def last_published_at(self):
        rows = await self._q("SELECT max(published_at) AS t FROM posts WHERE status='published'")
        return rows[0]["t"]

    # --- ретраи / AI / отправка ---
    async def claim_retry(self) -> Post | None:
        rows = await self._q(f"""
            UPDATE posts p SET status='processing', claimed_at=now(), attempts=attempts+1, updated_at=now()
            FROM automation_sources s
            WHERE s.id = p.source_id AND p.id = (
                SELECT id FROM posts WHERE status='pending' AND scheduled_at IS NULL AND cardinality(dest_msg_ids)=0
                  AND (next_attempt_at IS NULL OR next_attempt_at <= now())
                ORDER BY next_attempt_at NULLS FIRST, id FOR UPDATE SKIP LOCKED LIMIT 1)
            RETURNING {RET}""")
        return Post(**rows[0]) if rows else None

    async def set_post_schedule(self, pid, scheduled_at):
        rows = await self._q("""UPDATE posts SET scheduled_at=%s, status='candidate',
            next_attempt_at=NULL, attempts=0, last_error=NULL, updated_at=now()
            WHERE id=%s AND status IN ('candidate','pending','failed','expired')
            AND cardinality(dest_msg_ids)=0 AND send_started_at IS NULL RETURNING id""", (scheduled_at, pid))
        return bool(rows)

    async def claim_scheduled(self):
        rows = await self._q(f"""UPDATE posts p SET status='processing', claimed_at=now(),
            attempts=attempts+1, updated_at=now() FROM automation_sources s
            WHERE s.id=p.source_id AND p.id=(SELECT id FROM posts
                WHERE scheduled_at <= now() AND status IN ('candidate','pending')
                AND cardinality(dest_msg_ids)=0 AND send_started_at IS NULL
                AND (next_attempt_at IS NULL OR next_attempt_at <= now())
                ORDER BY scheduled_at, id FOR UPDATE SKIP LOCKED LIMIT 1)
            RETURNING {RET}""")
        return Post(**rows[0]) if rows else None

    async def claim_post_for_publish(self, pid: int) -> Post | None:
        """Publish now: берём пост в работу только если он реально ещё не отправлялся."""
        rows = await self._q(f"""UPDATE posts p SET status='processing', claimed_at=now(), attempts=attempts+1,
            updated_at=now() FROM automation_sources s WHERE s.id=p.source_id AND p.id=%s
            AND p.status IN ('candidate','pending','failed','expired') AND cardinality(p.dest_msg_ids)=0
            RETURNING {RET}""", (pid,))
        return Post(**rows[0]) if rows else None

    async def skip_post(self, pid: int) -> bool:
        rows = await self._q("""UPDATE posts SET status='skipped', updated_at=now()
            WHERE id=%s AND status IN ('candidate','pending','failed','expired')
            AND cardinality(dest_msg_ids)=0 RETURNING id""", (pid,))
        return bool(rows)

    async def set_ai(self, pid, status, caption=None, error=None):
        await self._q("UPDATE posts SET ai_status=%s, ai_caption=%s, ai_error=%s, updated_at=now() WHERE id=%s",
                      (status, caption, error, pid))

    async def next_caption_post(self):
        rows = await self._q("SELECT id FROM posts WHERE kind='parsed' AND status IN ('candidate','pending') "
                             "AND ai_status='unchecked' AND send_started_at IS NULL "
                             "AND cardinality(dest_msg_ids)=0 ORDER BY id LIMIT 1")
        return rows[0]['id'] if rows else None

    async def set_manual_caption(self, pid, caption):
        rows = await self._q("UPDATE posts SET ai_status='manual',ai_caption=%s,ai_error=NULL,updated_at=now() "
                             "WHERE id=%s AND status IN ('candidate','pending','failed','expired') "
                             "AND send_started_at IS NULL AND cardinality(dest_msg_ids)=0 RETURNING id", (caption, pid))
        return bool(rows)

    async def mark_send_started(self, pid):
        await self._q("UPDATE posts SET send_started_at=now(), updated_at=now() WHERE id=%s", (pid,))

    async def mark_published(self, pid, dest_ids: list[int]):
        await self._q("UPDATE posts SET status='published', dest_msg_ids=%s, published_at=now(), "
                        "last_error=NULL, updated_at=now() WHERE id=%s", (dest_ids, pid))

    async def record_sent(self, pid, dest_ids: list[int]):
        # Until the final batch completes, confirmed IDs represent a partial send.
        # Recovery must not call it published, and requeue must reject confirmed IDs.
        await self._q("UPDATE posts SET status='ambiguous', dest_msg_ids=%s, "
                      "last_error='send in progress: confirmed partial media', updated_at=now() WHERE id=%s",
                      (dest_ids, pid))

    async def mark(self, pid, status, error=None):
        await self._q("UPDATE posts SET status=%s, last_error=%s, updated_at=now() WHERE id=%s",
                      (status, error, pid))

    async def retry_later(self, pid, delay_sec: int, error: str):
        await self._q("UPDATE posts SET status='pending', send_started_at=NULL, last_error=%s, "
                      "next_attempt_at=now() + make_interval(secs => %s), updated_at=now() WHERE id=%s",
                      (error, delay_sec, pid))

    async def expire_old(self, hours: int) -> int:
        rows = await self._q("UPDATE posts SET status='expired', updated_at=now() "
                             "WHERE status IN ('candidate','pending') AND scheduled_at IS NULL AND kind='parsed' "
                             "AND source_date < now() - make_interval(hours => %s) RETURNING id", (hours,))
        return len(rows)

    async def requeue(self, pid) -> bool:
        rows = await self._q("UPDATE posts SET status='pending', send_started_at=NULL, next_attempt_at=NULL, "
                             "attempts=0, updated_at=now() WHERE id=%s AND status IN ('ambiguous','failed') "
                             "AND cardinality(dest_msg_ids)=0 RETURNING id", (pid,))
        return bool(rows)

    async def recover(self):
        rows = await self._q("SELECT id, status, send_started_at, dest_msg_ids FROM posts WHERE status='processing'")
        for r in rows:
            action = recovery_action(r["status"], r["send_started_at"] is not None, r["dest_msg_ids"])
            msg = {"published": None,
                   "ambiguous": "recovered: crashed after send started, verify channel then requeue",
                   PENDING: "recovered: crashed before send"}[action]
            await self.mark(r["id"], action, msg)
            log.warning("recovery post=%s -> %s", r["id"], action)
        n = await self._q("UPDATE posts SET ai_status='unchecked', ai_error='recovered after restart', "
                          "updated_at=now() WHERE ai_status='processing' RETURNING id")
        if n:
            log.warning("recovery: %d AI jobs reset to unchecked", len(n))

    # --- persistent dashboard actions ---
    async def create_action(self, kind: str, payload: dict | None = None, post_id: int | None = None) -> str:
        aid = str(uuid.uuid4())
        await self._q("INSERT INTO dashboard_actions(id, kind, payload, post_id) VALUES (%s,%s,%s,%s)",
                      (aid, kind, json.dumps(payload or {}), post_id))
        return aid

    async def get_action(self, aid: str):
        rows = await self._q("SELECT * FROM dashboard_actions WHERE id=%s", (aid,))
        return rows[0] if rows else None

    async def actions_page(self, limit: int = 50, offset: int = 0) -> list:
        return await self._q("SELECT * FROM dashboard_actions ORDER BY created_at DESC LIMIT %s OFFSET %s",
                             (limit, offset))

    async def actions_for_post(self, pid: int, limit: int = 20) -> list:
        return await self._q("SELECT * FROM dashboard_actions WHERE post_id=%s ORDER BY created_at DESC LIMIT %s",
                             (pid, limit))

    async def claim_action(self):
        rows = await self._q("""UPDATE dashboard_actions SET status='processing', claimed_at=now()
            WHERE id = (SELECT id FROM dashboard_actions WHERE status='pending'
                        ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
            RETURNING *""")
        return rows[0] if rows else None

    async def finish_action(self, aid: str, result: dict):
        await self._q("UPDATE dashboard_actions SET status='completed', result=%s, completed_at=now() WHERE id=%s",
                      (json.dumps(result or {}), aid))

    async def fail_action(self, aid: str, error: str):
        await self._q("UPDATE dashboard_actions SET status='failed', error=%s, completed_at=now() WHERE id=%s",
                      (error[:500], aid))

    async def fail_stale_actions(self, older_than_sec: int, error: str) -> list[dict]:
        """Зависший processing не должен висеть вечно: после рестарта/зависания -> failed."""
        return await self._q("""UPDATE dashboard_actions SET status='failed', error=%s, completed_at=now()
            WHERE status='processing'
              AND (claimed_at IS NULL OR claimed_at < now() - make_interval(secs => %s))
            RETURNING id, kind""", (error[:500], older_than_sec))

    # --- events ---
    async def add_event(self, type_: str, level: str = "info", post_id=None, source_id=None,
                        action_id=None, message: str = "", metadata=None):
        await self._q("INSERT INTO events(type, level, post_id, source_id, action_id, message, metadata) "
                      "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                      (type_, level, post_id, source_id, action_id, message or "",
                       json.dumps(metadata if metadata is not None else {}, ensure_ascii=False)))

    async def events_page(self, filters: dict, limit: int, offset: int) -> tuple[list, int]:
        where, args = build_events_where(filters or {})
        total = (await self._q(f"SELECT count(*) AS n FROM events WHERE {where}", args))[0]["n"]
        rows = await self._q(f"SELECT * FROM events WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s",
                             args + [limit, offset])
        return rows, total

    async def last_error_event(self):
        rows = await self._q("SELECT * FROM events WHERE level IN ('warning','error') ORDER BY id DESC LIMIT 1")
        return rows[0] if rows else None

    # --- внутреннее ---
    async def _load(self, pid) -> Post:
        r = await self._q(f"SELECT {RET} FROM posts p JOIN automation_sources s ON s.id=p.source_id WHERE p.id=%s", (pid,))
        return Post(**r[0])

    async def load_post(self, pid) -> Post | None:
        try:
            return await self._load(pid)
        except IndexError:
            return None
