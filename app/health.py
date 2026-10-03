"""Мини HTTP: /health (жив ли процесс), /ready (БД + Telegram)."""
from __future__ import annotations

import asyncio
import json
import time


async def serve(port: int, worker):
    async def handle(reader, writer):
        try:
            line = (await asyncio.wait_for(reader.readline(), 5)).decode(errors="ignore")
            path = line.split(" ")[1] if " " in line else "/"
            if path.startswith("/ready"):
                db_ok = await worker.db.ping()
                tg_ok = worker.client.is_connected()
                body = {"db": db_ok, "telegram": tg_ok,
                        "heartbeat_age_s": {k: round(time.time() - v) for k, v in worker.heartbeat.items()}}
                code = 200 if db_ok and tg_ok else 503
            else:
                body, code = {"status": "ok"}, 200
            data = json.dumps(body).encode()
            writer.write(f"HTTP/1.1 {code} X\r\nContent-Type: application/json\r\n"
                         f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n".encode() + data)
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "0.0.0.0", port)
    async with server:
        await server.serve_forever()
