import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from telethon import errors

from app.promo import PromoPublisher, candidate_groups, promo_slot


NOW = datetime(2026, 10, 4, 11, 0, tzinfo=timezone.utc)  # 14:00 Moscow


def msg(mid, hours=1, group=None, **kw):
    return NS(id=mid, date=NOW-timedelta(hours=hours), grouped_id=group,
              action=None, message='post', media=None, noforwards=False, **kw)


class SelectionTests(unittest.TestCase):
    def test_slots_use_moscow_and_do_not_catch_up_old_slots(self):
        self.assertIsNotNone(promo_slot(NOW))
        self.assertIsNotNone(promo_slot(NOW+timedelta(hours=6)))
        for delta in (-1, 16, 359, 376):
            self.assertIsNone(promo_slot(NOW+timedelta(minutes=delta)))

    def test_48_hours_album_and_settle(self):
        groups = candidate_groups([msg(1,48.01),msg(2,48),msg(3,1,7),msg(4,1,7),msg(5,0)],NOW)
        self.assertEqual(groups, [('m2',[2]),('g7',[3,4])])

    def test_protected_service_and_partial_boundary_album_are_excluded(self):
        protected=msg(1); protected.noforwards=True
        service=msg(2); service.action=object()
        self.assertEqual(candidate_groups([protected,service,msg(3,49,8),msg(4,47,8)],NOW), [])


class DB:
    def __init__(self): self.runs={}; self.retry_after=0
    async def kv_get(self, key, default=None): return self.retry_after
    async def promo_defer(self, slot, retry_after):
        self.retry_after=retry_after
        del self.runs[slot]
    async def promo_has_slot(self, slot): return slot in self.runs
    async def promo_used(self, ref): return {r['group'] for r in self.runs.values() if r['ref']==ref}
    async def promo_claim(self, slot, ref, group, ids):
        if slot in self.runs or (group is not None and group in await self.promo_used(ref)): return False
        self.runs[slot]={'ref':ref,'group':group,'ids':ids,'status':'sending'}
        return True
    async def promo_finish(self, slot, status, ids=(), error=None):
        self.runs[slot].update(status=status,dest_ids=list(ids),error=error)
    async def add_event(self,*a,**kw): pass


class PromoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db=DB(); self.messages=[msg(2),msg(1,49)]
        async def iterate(*a,**kw):
            for m in self.messages: yield m
        self.client=NS(iter_messages=iterate,forward_messages=AsyncMock(return_value=[NS(id=100)]))
        self.w=NS(db=self.db, client=self.client, cfg=NS(album_settle=60),
                  rt=NS(view=AsyncMock(return_value=NS(publishing_paused=False))),_dest=AsyncMock(return_value='dest'))
        self.p=PromoPublisher(self.w)
        self.resolve=patch('app.promo.resolve',AsyncMock(return_value=NS(noforwards=False)))
        self.resolve.start(); self.addCleanup(self.resolve.stop)

    async def test_forwards_once_and_restarts_do_not_duplicate(self):
        await self.p.tick(NOW); await PromoPublisher(self.w).tick(NOW)
        self.client.forward_messages.assert_awaited_once()
        args=self.client.forward_messages.call_args
        self.assertEqual(args.args,('dest',[2]))
        self.assertFalse(args.kwargs['drop_author'])
        self.assertEqual(self.db.runs[promo_slot(NOW)]['status'],'published')

    async def test_no_repeat_at_second_slot(self):
        await self.p.tick(NOW); await self.p.tick(NOW+timedelta(hours=6))
        self.assertEqual(self.client.forward_messages.await_count,1)
        self.assertEqual(self.db.runs[promo_slot(NOW+timedelta(hours=6))]['status'],'skipped')

    async def test_timeout_is_ambiguous_not_retried(self):
        self.client.forward_messages.side_effect=TimeoutError('uncertain')
        await self.p.tick(NOW); await self.p.tick(NOW)
        self.assertEqual(self.client.forward_messages.await_count,1)
        self.assertEqual(self.db.runs[promo_slot(NOW)]['status'],'ambiguous')

    async def test_pause_and_outside_schedule_do_nothing(self):
        await self.p.tick(NOW-timedelta(minutes=1))
        self.w.rt.view.return_value.publishing_paused=True
        await self.p.tick(NOW)
        self.assertFalse(self.db.runs)

    async def test_empty_selection_records_skip(self):
        self.messages=[]; await self.p.tick(NOW)
        self.assertEqual(self.db.runs[promo_slot(NOW)]['status'],'skipped')

    async def test_incomplete_forward_is_ambiguous(self):
        self.messages=[msg(2,1,7),msg(3,1,7)]
        await self.p.tick(NOW)
        self.assertEqual(self.db.runs[promo_slot(NOW)]['status'],'ambiguous')

    async def test_concurrent_ticks_only_send_once(self):
        await asyncio.gather(self.p.tick(NOW),PromoPublisher(self.w).tick(NOW))
        self.assertEqual(self.client.forward_messages.await_count,1)

    async def test_event_failure_does_not_prevent_send(self):
        self.db.add_event=AsyncMock(side_effect=ConnectionError('event database error'))
        with self.assertLogs('events',level='ERROR'):
            await self.p.tick(NOW)
        self.client.forward_messages.assert_awaited_once()
        self.assertEqual(self.db.runs[promo_slot(NOW)]['status'],'published')

    async def test_flood_wait_retries_only_after_persisted_cooldown(self):
        self.client.forward_messages.side_effect=[errors.FloodWaitError(None,60),[NS(id=101)]]
        await self.p.tick(NOW)
        self.assertFalse(self.db.runs)
        await PromoPublisher(self.w).tick(NOW+timedelta(seconds=30))
        self.assertEqual(self.client.forward_messages.await_count,1)
        await PromoPublisher(self.w).tick(NOW+timedelta(seconds=61))
        self.assertEqual(self.client.forward_messages.await_count,2)
        self.assertEqual(self.db.runs[promo_slot(NOW)]['status'],'published')

    async def test_permission_error_is_failed_not_ambiguous(self):
        self.client.forward_messages.side_effect=errors.ChatWriteForbiddenError(None)
        await self.p.tick(NOW)
        self.assertEqual(self.db.runs[promo_slot(NOW)]['status'],'failed')
