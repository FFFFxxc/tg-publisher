import test from 'node:test';
import assert from 'node:assert/strict';
import { QUEUE_VIEWS, queueApiStatus, queueHref, queueViewHref } from '../src/lib/queue.ts';

test('the queue presents exactly four modes supported by the posts API', () => {
  assert.deepEqual(QUEUE_VIEWS.map(({ value, label }) => [value, label]), [
    ['candidate', 'Готов к отбору'], ['failed', 'Ошибка'], ['skipped', 'Пропущен'], ['all', 'Все'],
  ]);
  assert.equal(queueApiStatus(''), 'candidate');
  for (const { value } of QUEUE_VIEWS) assert.equal(queueApiStatus(value), value);
});

test('switching mode keeps search and layout but drops legacy filters and page', () => {
  const old = { status: 'queued', media_type: 'video', source_id: '2', page: '4', q: 'тест & +', view: 'list' };
  const url = new URL(queueViewHref(old, 'skipped'), 'http://test.invalid');
  assert.deepEqual(Object.fromEntries(url.searchParams), { status: 'skipped', q: 'тест & +', view: 'list' });
  assert.equal(queueViewHref({}, 'candidate'), '/queue');
});

test('opening and paging a saved link keeps its precise technical filters', () => {
  assert.equal(queueApiStatus('ambiguous'), 'ambiguous');
  assert.equal(queueHref({status:'ambiguous', media_type:'video', view:'list'}, {}, 2),
    '/queue?status=ambiguous&media_type=video&view=list&page=2');
});
