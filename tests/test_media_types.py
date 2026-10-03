import unittest
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from telethon.tl import types as t
from app.media import media_type
from app.db import DB,build_posts_where,SCHEMA
from app.api import parse_posts_filters
from app.worker import Worker,msg_stats

def doc(mime,attrs=()):return SimpleNamespace(media=t.MessageMediaDocument(document=SimpleNamespace(mime_type=mime,attributes=list(attrs))))
def photo():return SimpleNamespace(media=t.MessageMediaPhoto(photo=None))

class MediaTests(unittest.TestCase):
 def test_photo_and_image_file(self):
  self.assertEqual(media_type([photo()]),'photo');self.assertEqual(media_type([doc('image/png')]),'photo')
 def test_video_and_animation(self):
  self.assertEqual(media_type([doc('video/mp4')]),'video');self.assertEqual(media_type([doc('application/octet-stream',[t.DocumentAttributeVideo(1,10,10)])]),'video');self.assertEqual(media_type([doc('image/gif',[t.DocumentAttributeAnimated()])]),'video')
 def test_albums_and_text(self):
  self.assertEqual(media_type([photo(),photo()]),'photo');self.assertEqual(media_type([photo(),doc('video/mp4')]),'mixed');self.assertEqual(media_type([SimpleNamespace(media=None)]),'text');self.assertEqual(media_type([doc('application/pdf')]),'document')
 def test_filters_validated_and_parameterized(self):
  f=parse_posts_filters({'kind':'repost','media_type':'video'});sql,args=build_posts_where(f);self.assertIn('p.media_type = %s',sql);self.assertEqual(args,['repost','video'])
  with self.assertRaises(ValueError):parse_posts_filters({'media_type':"video' OR TRUE"})
 def test_additive_migration(self):
  self.assertIn("ALTER TABLE posts ADD COLUMN IF NOT EXISTS media_type",SCHEMA);self.assertIn('ALTER TABLE own_posts ADD COLUMN IF NOT EXISTS media_type',SCHEMA)
 def test_album_metrics(self):
  msgs=[]
  for views,reactions,forwards,replies in [(100,3,4,2),(90,5,2,1)]:
   m=photo();m.views=views;m.forwards=forwards;m.replies=SimpleNamespace(replies=replies);m.reactions=SimpleNamespace(results=[SimpleNamespace(count=reactions)]);msgs.append(m)
  self.assertEqual(msg_stats(msgs),{'views':100,'reactions':8,'forwards':4,'replies':2,'media_type':'photo'})

class MediaDBTests(unittest.IsolatedAsyncioTestCase):
 async def test_archive_scan_uses_config_interval(self):
  import time
  w=object.__new__(Worker);w.cfg=SimpleNamespace(own_scan_hours=6);w.db=SimpleNamespace(kv_get=AsyncMock(return_value=str(time.time())));w._dest=AsyncMock()
  await w.scan_own(rt=SimpleNamespace());w._dest.assert_not_awaited()
 async def test_candidate_and_repost_store_format(self):
  db=object.__new__(DB);db._q=AsyncMock(return_value=[{'id':1}]);date=datetime.now(timezone.utc)
  st={'views':1,'reactions':2,'forwards':0,'replies':0,'media_type':'video'}
  await db.upsert_candidate(1,'m1',[1],date,'x',st,False);sql,args=db._q.call_args.args;self.assertIn('media_type',sql);self.assertEqual(args[-1],'video')
  await db.create_repost_from_own(1,'m1',[1],date,'x',2);sql,args=db._q.call_args.args;self.assertIn('SELECT media_type FROM own_posts',sql);self.assertEqual(args[7],'m1')
 async def test_existing_posts_classified_without_download(self):
  w=object.__new__(Worker);w.db=SimpleNamespace(unclassified_posts=AsyncMock(return_value=[{'id':5,'ref':'@source','source_msg_ids':[42]}]),set_media_type=AsyncMock());m=doc('video/mp4');m.id=42
  w.client=SimpleNamespace(get_messages=AsyncMock(return_value=[m]),download_media=AsyncMock())
  with patch('app.worker.resolve',new=AsyncMock(return_value='entity')):await w.refresh_media_types()
  w.db.set_media_type.assert_awaited_once_with(5,'video');w.client.download_media.assert_not_awaited()

if __name__=='__main__':unittest.main()
