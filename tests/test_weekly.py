import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from telethon import errors
from telethon.tl.types import MessageEntityCustomEmoji, MessageEntityTextUrl, MessageMediaPhoto

from app.weekly import EMOJI_ID, TARGET, WeeklyPublisher, daily_times, ranked_groups, weekly_slot
from app.db import DB as RealDB
from app.logic import u16

NOW = datetime(2026, 10, 4, 9, tzinfo=timezone.utc)  # 12:00 Moscow


def msg(mid, hours=1, group=None, reactions=0, views=0, **kw):
    return NS(id=mid, date=NOW-timedelta(hours=hours), grouped_id=group, action=None,
              message='text', media=None, noforwards=False, views=views, forwards=0,
              reactions=NS(results=[NS(count=reactions)]), **kw)


class SelectionTests(unittest.TestCase):
    def test_stable_quota_and_slots_for_30_days(self):
        counts = set()
        for day in range(30):
            now = NOW+timedelta(days=day)
            times = daily_times(now)
            counts.add(len(times))
            self.assertEqual(times, daily_times(now+timedelta(hours=3)))
            self.assertTrue(1 <= len(times) <= 3)
            slots = {weekly_slot(now+timedelta(minutes=i)) for i in range(24*60) if weekly_slot(now+timedelta(minutes=i))}
            # Start at Moscow noon: count only today's slots (next day noon excluded).
            self.assertEqual(len(slots), len(times))
        self.assertEqual(counts, {1, 2, 3})
        self.assertIsNone(weekly_slot(NOW-timedelta(minutes=1)))
        self.assertIsNotNone(weekly_slot(NOW+timedelta(minutes=16)))

    def test_ranks_reactions_then_views_and_albums(self):
        rows = ranked_groups([msg(1,reactions=3,views=10000),msg(2,reactions=5,views=2),
                              msg(3,group=7,reactions=3),msg(4,group=7,reactions=4)],NOW)
        self.assertEqual([r[1] for r in rows], ['g7','m2','m1'])
        self.assertEqual([m.id for m in rows[0][2]],[3,4])
        rows = ranked_groups([msg(5,reactions=5,views=1),msg(6,reactions=5,views=10)],NOW)
        self.assertEqual(rows[0][1],'m6')

    def test_week_boundary_settle_and_protected(self):
        protected=msg(1);protected.noforwards=True
        service=msg(2);service.action=object()
        rows=ranked_groups([protected,service,msg(3,169,9),msg(4,167,9),msg(5,168),msg(6,0)],NOW)
        self.assertEqual([r[1] for r in rows],['m5'])


class DB:
    def __init__(self): self.runs={};self.cooldown=0;self.rejections=set()
    async def weekly_recover(self): pass
    async def weekly_start_send(self,slot):
        self.runs[slot]['status']='sending';return True
    async def weekly_has_slot(self,slot): return slot in self.runs
    async def weekly_used(self,ref): return {r['key'] for r in self.runs.values() if r['ref']==ref} | self.rejections
    async def kv_get(self,*a): return self.cooldown
    async def kv_set(self,k,v): self.cooldown=v
    async def weekly_claim(self,slot,ref,key,ids):
        if slot in self.runs or (key is not None and key in await self.weekly_used(ref)): return False
        self.runs[slot]={'ref':ref,'key':key,'ids':ids,'status':'preparing'};return True
    async def weekly_reject(self,slot,error):
        self.rejections.add(self.runs[slot]['key']);del self.runs[slot]
    async def weekly_finish(self,slot,status,ids=(),error=None): self.runs[slot].update(status=status,dest_ids=list(ids),error=error)
    async def weekly_defer(self,slot,retry_after): self.cooldown=retry_after;del self.runs[slot]
    async def add_event(self,*a,**kw): pass


class PublisherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db=DB();self.messages=[msg(2,reactions=8),msg(1,reactions=2)]
        async def iterate(*a,**kw):
            for m in self.messages: yield m
        self.client=NS(iter_messages=iterate,send_message=AsyncMock(return_value=NS(id=101)),
                       send_file=AsyncMock(return_value=[NS(id=101)]))
        self.w=NS(db=self.db,client=self.client,cfg=NS(destination='private',album_settle=60,max_media_mb=200,premium=True),
                  rt=NS(view=AsyncMock(return_value=NS(publishing_paused=False))),
                  _dest=AsyncMock(return_value=NS(noforwards=False)),
                  _valid_custom_emojis=AsyncMock(side_effect=lambda e:e))
        self.p=WeeklyPublisher(self.w)
        self.patch=patch('app.weekly.resolve',AsyncMock(return_value='public'))
        self.patch.start();self.addCleanup(self.patch.stop)

    async def test_best_once_concurrency_restart(self):
        await asyncio.gather(self.p.tick(NOW),WeeklyPublisher(self.w).tick(NOW))
        await WeeklyPublisher(self.w).tick(NOW)
        self.client.send_message.assert_awaited_once()
        row=self.db.runs[weekly_slot(NOW)]
        self.assertEqual(row['ids'],[2]);self.assertEqual(row['status'],'published')
        self.assertEqual(self.client.send_message.call_args.args[0],'public')

    async def test_caption_custom_emoji_bold_link_and_arrow(self):
        await self.p.tick(NOW)
        args=self.client.send_message.call_args
        text=args.args[1];entities=args.kwargs['formatting_entities']
        self.assertIn('Весь наш контент',text);self.assertTrue(text.endswith(' ☝️'))
        emoji=next(e for e in entities if isinstance(e,MessageEntityCustomEmoji))
        self.assertEqual(emoji.document_id,EMOJI_ID)
        link=next(e for e in entities if isinstance(e,MessageEntityTextUrl))
        self.assertEqual(link.url,'https://t.me/comics_komixy/29')
        self.assertEqual(text.encode('utf-16-le')[link.offset*2:(link.offset+link.length)*2].decode('utf-16-le'),'Весь наш контент')
        self.assertEqual(TARGET,'@comics_komixy')

    async def test_no_repeat_next_day(self):
        await self.p.tick(NOW);await self.p.tick(NOW+timedelta(days=1))
        self.assertEqual(self.client.send_message.await_count,2)
        self.assertEqual(self.db.runs[weekly_slot(NOW+timedelta(days=1))]['ids'],[1])

    async def test_empty_and_paused(self):
        self.w.rt.view.return_value.publishing_paused=True
        await self.p.tick(NOW);self.assertFalse(self.db.runs)
        self.w.rt.view.return_value.publishing_paused=False;self.messages=[]
        await self.p.tick(NOW)
        self.assertEqual(self.db.runs[weekly_slot(NOW)]['status'],'skipped')
        self.client.send_message.assert_not_awaited()

    async def test_source_protected_not_copied(self):
        self.w._dest.return_value.noforwards=True
        with self.assertRaises(ValueError): await self.p.tick(NOW)
        self.client.send_message.assert_not_awaited();self.assertFalse(self.db.runs)

    async def test_timeout_retains_reservation(self):
        self.client.send_message.side_effect=TimeoutError('uncertain')
        await self.p.tick(NOW);await self.p.tick(NOW)
        self.assertEqual(self.db.runs[weekly_slot(NOW)]['status'],'ambiguous')
        self.client.send_message.assert_awaited_once()

    async def test_flood_wait_persisted_and_slot_released(self):
        self.client.send_message.side_effect=errors.FloodWaitError(None,capture=30)
        await self.p.tick(NOW);await self.p.tick(NOW)
        self.assertFalse(self.db.runs);self.assertGreaterEqual(self.db.cooldown,NOW.timestamp()+30)
        self.client.send_message.assert_awaited_once()

    async def test_failed_preparation_does_not_publish(self):
        with patch.object(self.p,'prepare',AsyncMock(side_effect=ValueError('file too big'))):
            await self.p.tick(NOW)
        self.assertFalse(self.db.runs);self.client.send_message.assert_not_awaited()
        self.assertGreaterEqual(self.db.cooldown,NOW.timestamp()+300)

    async def test_media_upload_album_counts_as_one_and_partial_no_retry(self):
        self.messages=[msg(1,group=7),msg(2,group=7)]
        with patch.object(self.p,'prepare',AsyncMock(return_value=([[object(),object()]],'signature',[]))):
            await self.p.tick(NOW);await self.p.tick(NOW)
        self.client.send_file.assert_awaited_once()
        self.assertEqual(self.db.runs[weekly_slot(NOW)]['status'],'ambiguous')
        self.assertEqual(self.db.runs[weekly_slot(NOW)]['dest_ids'],[101])

    async def test_media_prepared_without_private_caption(self):
        import tempfile
        m=msg(1);m.media=MessageMediaPhoto(photo=None);m.message='private invitation'
        self.client.download_media=AsyncMock(return_value='image.jpg')
        with tempfile.TemporaryDirectory() as tmp, patch('app.weekly.prepare_media',AsyncMock(return_value='prepared')):
            batches,caption,_=await self.p.prepare([m],tmp)
        self.assertEqual(batches,[['prepared']]);self.assertNotIn('private invitation',caption)

    async def test_partial_flood_is_not_retried(self):
        self.client.send_file.side_effect=[[NS(id=101)],errors.FloodWaitError(None,capture=30)]
        with patch.object(self.p,'prepare',AsyncMock(return_value=([[object()],[object()]],'signature',[]))):
            await self.p.tick(NOW);await self.p.tick(NOW)
        self.assertEqual(self.client.send_file.await_count,2)
        self.assertEqual(self.db.runs[weekly_slot(NOW)]['status'],'ambiguous')

    async def test_text_caption_respects_utf16_limit(self):
        import tempfile
        m=msg(1);m.message='😀'*4096
        with tempfile.TemporaryDirectory() as tmp:
            _,caption,entities=await self.p.prepare([m],tmp)
        self.assertLessEqual(u16(caption),4096)
        self.assertTrue(caption.endswith('Весь наш контент ☝️'))
        self.assertTrue(all(e.offset+e.length <= u16(caption) for e in entities))

    async def test_definite_rpc_rejection_not_ambiguous(self):
        self.client.send_message.side_effect=errors.ChatWriteForbiddenError(None)
        await self.p.tick(NOW)
        self.assertFalse(self.db.runs)
        self.assertEqual(self.db.rejections,{'m2'})
        self.client.send_message.side_effect=None
        await self.p.tick(NOW+timedelta(seconds=30))
        self.assertEqual(self.db.runs[weekly_slot(NOW)]['ids'],[1])
        self.assertEqual(self.db.runs[weekly_slot(NOW)]['status'],'published')

    async def test_restart_catches_up_todays_slots_with_spacing(self):
        now=next(NOW+timedelta(days=i) for i in range(30) if len(daily_times(NOW+timedelta(days=i)))==3)
        self.messages=[msg(i,reactions=i) for i in range(1,4)]
        for m in self.messages: m.date=now-timedelta(hours=1)
        late=now+timedelta(hours=9)
        await self.p.tick(late)
        await WeeklyPublisher(self.w).tick(late+timedelta(minutes=1))
        self.client.send_message.assert_awaited_once()
        await WeeklyPublisher(self.w).tick(late+timedelta(minutes=31))
        await WeeklyPublisher(self.w).tick(late+timedelta(minutes=62))
        await WeeklyPublisher(self.w).tick(late+timedelta(minutes=93))
        self.assertEqual(self.client.send_message.await_count,3)
        self.assertEqual(len(self.db.runs),3)


class RecoverySQLTests(unittest.IsolatedAsyncioTestCase):
    async def test_presend_released_postsend_preserved(self):
        db=object.__new__(RealDB);db._q=AsyncMock(return_value=[{'slot':'s'}])
        await db.weekly_recover()
        calls=db._q.call_args_list
        self.assertIn("status='preparing' AND send_started_at IS NULL",calls[0].args[0])
        self.assertIn("20 minutes",calls[0].args[0])
        self.assertIn("status='ambiguous'",calls[1].args[0])
        self.assertIn("status='sending'",calls[1].args[0])
        self.assertTrue(await db.weekly_start_send('s'))
        self.assertIn("send_started_at=now()",db._q.call_args.args[0])
        self.assertIn("status='preparing'",db._q.call_args.args[0])


if __name__=='__main__': unittest.main()
