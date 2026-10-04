"""Independent network-channel forwards, preserving original author and caption."""
from __future__ import annotations

import asyncio
import random
from time import monotonic
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from telethon import errors

from . import events
from .logic import due_slot, group_messages
from .tg import resolve
from .networks import defaults, load_settings

SOURCE = '@anime_edit_videoo'
TIMES = (time(14), time(20))
TZ = ZoneInfo('Europe/Moscow')


def promo_slot(now, settings=None):
    times = TIMES if settings is None else [time.fromisoformat(t) for t in settings['times']]
    return due_slot(now.astimezone(TZ), times)


def candidate_groups(messages, now, settle_seconds=60, lookback_hours=48):
    by_id = {m.id: m for m in messages}
    earliest = now - timedelta(hours=lookback_hours)
    settled = now - timedelta(seconds=settle_seconds)
    result = []
    for key, ids in group_messages([(m.id, m.grouped_id) for m in messages]):
        group = [by_id[mid] for mid in ids]
        if all(earliest <= m.date <= settled and not m.action and
               not getattr(m, 'noforwards', False) and (m.message or m.media) for m in group):
            result.append((key, ids))
    return result


class PromoPublisher:
    def __init__(self, worker):
        self.w = worker

    async def candidates(self, now, settings=None):
        settings = settings or await load_settings(self.w.db, self.w.cfg, 'promo')
        source_ref = settings['source_ref']
        entity = await resolve(self.w.client, source_ref)
        if getattr(entity, 'noforwards', False):
            raise ValueError('Источник запрещает пересылку')
        messages = []
        cutoff = now - timedelta(hours=settings['lookback_hours'])
        # Read to the date boundary, not an arbitrary latest-N sample. Keep the
        # entire boundary album so an album crossing 48h is excluded as a unit.
        boundary_group = None
        async for m in self.w.client.iter_messages(entity, limit=None):
            if m.date < cutoff:
                if boundary_group is None:
                    boundary_group = m.grouped_id
                elif m.grouped_id != boundary_group:
                    break
                messages.append(m)
                if boundary_group is None:
                    break
            else:
                messages.append(m)
        groups = candidate_groups(messages, now, self.w.cfg.album_settle, settings['lookback_hours'])
        used = await self.w.db.promo_used(source_ref)
        return entity, [(key, ids) for key, ids in groups if key not in used]

    async def tick(self, now=None):
        started = monotonic()
        now = now or datetime.now(timezone.utc)
        settings = await load_settings(self.w.db, self.w.cfg, 'promo')
        source_ref = settings['source_ref']
        slot = promo_slot(now, settings)
        if not settings['enabled'] or not slot or (await self.w.rt.view()).publishing_paused:
            return
        db = self.w.db
        if now.timestamp() < float(await db.kv_get('promo_retry_after', 0)):
            return
        if await db.promo_has_slot(slot):
            return
        entity, choices = await self.candidates(now, settings)
        if not choices:
            if await db.promo_claim(slot, source_ref, None, []):
                await db.promo_finish(slot, 'skipped', error=f"Нет новых постов за последние {settings['lookback_hours']} часов")
                await events.log_event(db, 'promo_skipped', message=f'{slot}: нет подходящих постов')
            return
        target_ref = settings['target_ref']
        dest = await self.w._dest() if not target_ref or target_ref == getattr(self.w.cfg, 'destination', '') else await resolve(self.w.client, target_ref)
        if await load_settings(self.w.db, self.w.cfg, 'promo') != settings or (await self.w.rt.view()).publishing_paused:
            return
        key, ids = random.choice(choices)
        # Atomic uniqueness on both slot and source/group. Persist BEFORE the
        # Telegram RPC. A crash leaves sending, which is never blindly retried.
        if not await db.promo_claim(slot, source_ref, key, ids):
            return
        await events.log_event(db, 'promo_started', message=f'{slot}: {source_ref}',
                               metadata={'source_ids': ids})
        sent_ids = []
        try:
            sent = await asyncio.wait_for(self.w.client.forward_messages(
                dest, ids, from_peer=entity, drop_author=False), timeout=120)
            sent = sent if isinstance(sent, list) else [sent]
            sent_ids = [m.id for m in sent if m is not None]
            if len(sent_ids) != len(ids):
                raise RuntimeError('Не все сообщения репоста подтверждены Telegram')
        except errors.FloodWaitError as exc:
            # Telegram explicitly rejected this call: nothing was forwarded.
            # Persist cooldown and release the slot atomically, so another loop
            # or restarted worker cannot retry before Telegram allows it.
            await db.promo_defer(slot, now.timestamp() + (monotonic() - started) + max(1, exc.seconds))
            await events.log_event(db, 'promo_deferred', level='warning',
                                   message=f'{slot}: FloodWait {exc.seconds}s')
            return
        except (errors.ChatWriteForbiddenError, errors.ChatAdminRequiredError,
                errors.ChatForwardsRestrictedError, errors.MessageIdInvalidError) as exc:
            await db.promo_finish(slot, 'failed', error=type(exc).__name__)
            await events.log_event(db, 'promo_failed', level='error', message=f'{slot}: {type(exc).__name__}')
            return
        except Exception as exc:
            # Even a timeout may follow an accepted send. Retain the reservation
            # and any confirmed IDs instead of duplicating an advertisement.
            await db.promo_finish(slot, 'ambiguous', sent_ids, f'{type(exc).__name__}: {exc}')
            await events.log_event(db, 'promo_ambiguous', level='error', message=f'{slot}: {type(exc).__name__}')
            return
        await db.promo_finish(slot, 'published', sent_ids)
        await events.log_event(db, 'promo_published', message=f'{slot}: репост {source_ref}',
                               metadata={'source_ids': ids, 'dest_ids': sent_ids})
