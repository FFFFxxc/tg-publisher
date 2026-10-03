"""Общие фейки для офлайн-тестов: БД, воркер, конфиг. Без сети и без PostgreSQL."""
from __future__ import annotations

import time
import uuid
from datetime import time as dtime
from types import SimpleNamespace

from app.config import Config
from app.logic import DEFAULT_FOOTER, Post


def make_cfg(**kw) -> Config:
    defaults = dict(
        api_id=1, api_hash="hash", session="", destination="@dest", sources=[], proxy=None,
        database_url="postgresql://u:p@localhost/db", publish_times=[dtime(9, 0), dtime(12, 0)],
        schedule_pattern=["parsed", "old"], ai_api_key="sk-abcdef123456",
        ai_base_url="https://ai.example/v1", ai_model="test-model", ai_prompt="test prompt",
        tz_name="Europe/Moscow", footer=DEFAULT_FOOTER,
    )
    defaults.update(kw)
    return Config(**defaults)


PROXY = {"proxy_type": "socks5", "addr": "127.0.0.1", "port": 1080, "rdns": True}


def make_post(pid=1, status="candidate", dest=None, kind="parsed", **kw) -> dict:
    d = {"id": pid, "kind": kind, "source_id": 1, "source_ref": "@src", "source_msg_ids": [10],
         "text": "hello", "status": status, "ai_status": "not_needed", "ai_caption": None, "ai_error": None,
         "dest_msg_ids": dest or [], "send_started_at": None, "attempts": 0, "next_attempt_at": None,
         "last_error": None, "claimed_at": None, "published_at": None, "created_at": "now",
         "updated_at": "now", "views": 0, "reactions": 0, "forwards": 0, "replies": 0, "score": None,
         "source_title": None, "group_key": f"m{pid}", "source_date": "now"}
    d.update(kw)
    return d


def to_post(row: dict) -> Post:
    return Post(id=row["id"], kind=row["kind"], source_id=row["source_id"], source_ref=row["source_ref"],
                source_msg_ids=list(row["source_msg_ids"]), text=row["text"], ai_status=row["ai_status"],
                ai_caption=row["ai_caption"], attempts=row["attempts"])


class FakeDB:
    def __init__(self):
        self.schema = "tg_publisher"
        self.kv: dict = {}
        self.sources: list[dict] = []
        self.posts: list[dict] = []
        self.own: list[dict] = []
        self.events: list[dict] = []
        self.actions: list[dict] = []
        self.last_posts_filters = None

    async def ping(self):
        return True

    # kv
    async def kv_get(self, k, default=None):
        return self.kv.get(k, default)

    async def kv_set(self, k, v):
        self.kv[k] = str(v)

    async def kv_prefix(self, prefix):
        return {k[len(prefix):]: v for k, v in self.kv.items() if k.startswith(prefix)}

    # sources
    async def sources(self, only_enabled=True):
        return [s for s in self.sources if s["role"] == "source" and (s["enabled"] or not only_enabled)]

    async def get_source(self, sid):
        return next((s for s in self.sources if s["id"] == sid and s["role"] == "source"), None)

    async def enabled_sources_count(self):
        return sum(1 for s in self.sources if s["role"] == "source" and s["enabled"])

    async def add_source_checked(self, ref, title):
        for s in self.sources:
            if s["ref"] == ref:
                return s["id"], False
        sid = 100 + len(self.sources)
        self.sources.append({"id": sid, "ref": ref, "role": "source", "enabled": True, "title": title,
                             "last_message_id": None, "last_error": None})
        return sid, True

    async def set_source_enabled(self, sid, enabled):
        for s in self.sources:
            if s["id"] == sid and s["role"] == "source":
                s["enabled"] = enabled
                return True
        return False

    async def delete_source(self, sid):
        for i, s in enumerate(self.sources):
            if s["id"] == sid and s["role"] == "source":
                if s.get("has_posts"):
                    return "has_posts"
                del self.sources[i]
                return "deleted"
        return "missing"

    async def set_source_cursor(self, sid, last_id, error=None):
        s = await self.get_source(sid)
        if s:
            s["last_message_id"], s["last_error"] = last_id, error

    async def set_source_title(self, sid, title):
        s = await self.get_source(sid)
        if s:
            s["title"] = title

    # posts
    async def posts_page(self, filters, limit, offset):
        self.last_posts_filters = dict(filters or {})
        items = list(self.posts)
        f = filters or {}
        for key in ("status", "kind", "ai_status"):
            if f.get(key):
                items = [p for p in items if p[key] == f[key]]
        if f.get("source_id"):
            items = [p for p in items if p["source_id"] == f["source_id"]]
        return items[offset:offset + limit], len(items)

    async def get_post(self, pid):
        return next((p for p in self.posts if p["id"] == pid), None)

    async def counts_by_status(self):
        out = {}
        for p in self.posts:
            out[p["status"]] = out.get(p["status"], 0) + 1
        return out

    async def published_stats(self, today_start):
        return {"today": 1, "h24": 2}

    async def last_published_at(self):
        ts = [p["published_at"] for p in self.posts if p["status"] == "published" and p["published_at"]]
        return max(ts) if ts else None

    async def claim_post_for_publish(self, pid):
        p = await self.get_post(pid)
        if p and p["status"] in ("candidate", "pending", "failed", "expired") and not p["dest_msg_ids"]:
            p["status"] = "processing"
            return to_post(p)
        return None

    async def requeue(self, pid):
        p = await self.get_post(pid)
        if p and p["status"] in ("failed", "ambiguous") and not p["dest_msg_ids"]:
            p["status"] = "pending"
            return True
        return False

    async def skip_post(self, pid):
        p = await self.get_post(pid)
        if p and p["status"] in ("candidate", "pending", "failed", "expired") and not p["dest_msg_ids"]:
            p["status"] = "skipped"
            return True
        return False

    async def set_ai(self, pid, status, caption=None, error=None):
        p = await self.get_post(pid)
        if p:
            p["ai_status"], p["ai_caption"], p["ai_error"] = status, caption, error

    async def load_post(self, pid):
        p = await self.get_post(pid)
        return to_post(p) if p else None

    async def backfill_candidates(self, sid, items, ai_enabled):
        existing = {(p["source_id"], p.get("group_key")) for p in self.posts}
        n = 0
        for key, ids, date, text, st in items:
            if (sid, key) in existing:
                continue
            p = make_post(pid=1000 + len(self.posts), status="candidate")
            p.update({"source_id": sid, "group_key": key, "source_msg_ids": list(ids), "text": text})
            self.posts.append(p)
            n += 1
        return n

    # own
    async def own_page(self, order="reactions", limit=50, offset=0):
        return list(self.own)[offset:offset + limit], len(self.own)

    async def get_own(self, key):
        return next((o for o in self.own if o["group_key"] == key), None)

    async def own_count(self):
        return len(self.own)

    async def mark_own_reposted(self, key):
        o = await self.get_own(key)
        if o:
            o["last_reposted_at"] = "now"

    async def create_repost_from_own(self, own_sid, key, ids, date, text, reactions):
        for p in self.posts:
            if p["kind"] == "repost" and (set(p["dest_msg_ids"]) & set(ids)
                                          or p["source_msg_ids"] == list(ids)):
                return None
        pid = 2000 + len(self.posts)
        p = make_post(pid=pid, status="candidate", kind="repost")
        p.update({"source_id": own_sid, "source_msg_ids": list(ids), "text": text})
        self.posts.append(p)
        return pid

    # actions
    async def create_action(self, kind, payload=None, post_id=None):
        aid = uuid.uuid4().hex
        self.actions.append({"id": aid, "kind": kind, "payload": payload or {}, "status": "pending",
                             "post_id": post_id, "result": None, "error": None, "created_at": "now",
                             "claimed_at": None, "completed_at": None})
        return aid

    async def get_action(self, aid):
        return next((a for a in self.actions if a["id"] == aid), None)

    async def actions_page(self, limit=50, offset=0):
        return list(reversed(self.actions))[offset:offset + limit]

    async def actions_for_post(self, pid, limit=20):
        return [a for a in reversed(self.actions) if a["post_id"] == pid][:limit]

    async def claim_action(self):
        for a in self.actions:
            if a["status"] == "pending":
                a["status"] = "processing"
                a["claimed_at"] = time.time()
                return dict(a)
        return None

    async def finish_action(self, aid, result):
        a = await self.get_action(aid)
        a.update({"status": "completed", "result": result, "completed_at": "now"})

    async def fail_action(self, aid, error):
        a = await self.get_action(aid)
        a.update({"status": "failed", "error": error, "completed_at": "now"})

    async def fail_stale_actions(self, older_than_sec, error):
        out, cutoff = [], time.time() - older_than_sec
        for a in self.actions:
            if a["status"] == "processing" and (a["claimed_at"] is None or a["claimed_at"] < cutoff):
                a.update({"status": "failed", "error": error, "completed_at": "now"})
                out.append({"id": a["id"], "kind": a["kind"]})
        return out

    # events
    async def add_event(self, type_, level="info", post_id=None, source_id=None, action_id=None,
                        message="", metadata=None):
        self.events.append({"id": len(self.events) + 1, "type": type_, "level": level, "post_id": post_id,
                            "source_id": source_id, "action_id": action_id, "message": message,
                            "metadata": metadata or {}, "created_at": "now"})

    async def events_page(self, filters, limit, offset):
        items = list(self.events)
        f = filters or {}
        for key in ("type", "level"):
            if f.get(key):
                items = [e for e in items if e[key] == f[key]]
        for key in ("post_id", "source_id"):
            if f.get(key):
                items = [e for e in items if e[key] == f[key]]
        return list(reversed(items))[offset:offset + limit], len(items)

    async def last_error_event(self):
        errs = [e for e in self.events if e["level"] in ("warning", "error")]
        return errs[-1] if errs else None


class FakeWorker:
    """Утиная типизация вместо наследования Worker: actions.py работает с атрибутами."""

    def __init__(self, db: FakeDB, cfg: Config):
        from app.settings import RuntimeSettings
        self.db, self.cfg = db, cfg
        self.rt = RuntimeSettings(db, cfg, ttl=0)
        self.client = SimpleNamespace(is_connected=lambda: True)
        self.heartbeat = {"collect": time.time(), "publish": time.time(), "actions": time.time()}
        self.ran: list[int] = []
        self.scan_calls = 0

    async def _run(self, post):
        self.ran.append(post.id)

    async def scan_own(self, force=False, rt=None):
        self.scan_calls += 1

    async def _own_sid(self):
        return 7

    async def _preview_image(self, msgs, files, tmp):
        return None

    async def _ai(self, post, image, rt):
        await self.db.set_ai(post.id, "generated", "ai caption", None)
        return "ai caption"
