"""CLI: login | run | verify | test-media <source> <msg_id> | test-footer | scan-own | top-old | add-source <ref> | requeue <post_id>"""
from __future__ import annotations

import asyncio
import logging
import sys
import tempfile

from .config import Config, ConfigError


async def main(argv):
    cmd = argv[0] if argv else "run"
    cfg = Config.from_env()
    from .db import DB
    from .tg import build_client, ensure_connected, resolve
    client = build_client(cfg)
    if cmd == "login":
        # единственный интерактивный шаг: номер, код, 2FA. Сессия ложится в volume.
        await client.start()
        me = await client.get_me()
        print(f"logged in as id={me.id}. Now: docker compose up -d")
        await client.disconnect()
        return
    db = DB(cfg.database_url, cfg.db_schema)
    await db.open()
    try:
        if cmd == "run":
            from .activity import ActivityAccounts
            from .api import ApiContext, serve as serve_api
            from .health import serve
            from .settings import RuntimeSettings
            from .worker import Worker
            w = Worker(cfg, db, client, RuntimeSettings(db, cfg))
            w.activity = ActivityAccounts(cfg, db, approver=client)
            tasks = [w.run(), w.activity.run(), serve(cfg.health_port, w)]
            if cfg.control_api_token:
                tasks.append(serve_api(cfg.control_api_port, ApiContext(w), cfg.control_api_token))
                print(f"control api: http://127.0.0.1:{cfg.control_api_port} (bearer auth on)")
            else:
                print("CONTROL_API_TOKEN is not set: control api disabled "
                      "(веб-панель не сможет подключиться)")
            try:
                await asyncio.gather(*tasks)
            finally:
                await w.activity.close()
        elif cmd == "verify":
            await ensure_connected(client)
            print("auth: ok | transport:", "socks5" if cfg.proxy else "direct",
                  "| client proxy:", "set" if getattr(client, "_proxy", None) else "none")
            print("db: ok" if await db.ping() else "db: FAIL")
            for ref in cfg.sources:
                print(f"[from TG_SOURCES] {ref}:", await _probe(client, ref))
            for s in await db.sources(only_enabled=False):
                print(f"[db source #{s['id']} enabled={s['enabled']}] {s['ref']}:", await _probe(client, s["ref"]))
            print("destination:", await _probe(client, cfg.destination))
        elif cmd == "test-media":
            await ensure_connected(client)
            src, mid = argv[1], int(argv[2])
            m = await client.get_messages(await resolve(client, src), ids=mid)
            if not m or not m.media:
                sys.exit("message not found or has no media")
            media = m.photo or m.document
            print("media dc:", getattr(media, "dc_id", "?"), "| session dc:", client.session.dc_id)
            with tempfile.TemporaryDirectory() as d:
                path = await client.download_media(m, file=d + "/")
                import os
                print("downloaded:", os.path.basename(path), os.path.getsize(path), "bytes (FileMigrate path OK)")
        elif cmd == "test-footer":
            # шлёт подпись в «Избранное», чтобы глазами проверить премиум-эмодзи и ссылки
            await ensure_connected(client)
            from .logic import build_caption
            from .worker import to_entities
            text, _, specs = build_caption("Тест подписи", None, cfg.footer, False)
            await client.send_message("me", text, formatting_entities=to_entities(specs), parse_mode=None,
                                      link_preview=False)
            print("sent to Saved Messages. If emoji are plain, the account has no Telegram Premium.")
        elif cmd == "scan-own":
            await ensure_connected(client)
            from .worker import Worker
            await Worker(cfg, db, client).scan_own(force=True)
        elif cmd == "top-old":
            rows = await db._q("SELECT group_key, post_date, reactions, views, last_reposted_at FROM own_posts "
                               "ORDER BY reactions DESC LIMIT 15")
            for r in rows:
                print(r["group_key"], r["post_date"].date(), "reactions", r["reactions"], "views", r["views"],
                      "reposted", r["last_reposted_at"])
        elif cmd == "add-source":
            await db.ensure_source(argv[1]); print("added", argv[1])
        elif cmd == "requeue":
            print("requeued" if await db.requeue(int(argv[1])) else "not requeued (wrong status or already sent)")
        else:
            sys.exit(__doc__)
    finally:
        if client.is_connected():
            await client.disconnect()
        await db.close()


async def _probe(client, ref):
    try:
        e = await resolve(client, ref)
        msgs = await client.get_messages(e, limit=1)
        return f"ok (last id {msgs[0].id if msgs else '-'})"
    except Exception as ex:
        return f"FAIL {type(ex).__name__}: {ex}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("telethon").setLevel(logging.WARNING)
    try:
        asyncio.run(main(sys.argv[1:]))
    except ConfigError as e:
        sys.exit(f"config error: {e}")
