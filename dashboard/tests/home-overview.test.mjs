import test from 'node:test';
import assert from 'node:assert/strict';
import { homeDate, homeSlot } from '../src/lib/homeOverview.ts';

const now = new Date('2026-11-19T21:10:00Z');

test('date is the Moscow day rather than the server UTC day', () => {
  assert.equal(homeDate(now), '20 ноября 2026');
});

test('manual and retry timestamps are preferred to default slots', () => {
  assert.deepEqual(homeSlot({scheduled_at:'2026-11-20T09:00:00Z'}, {next_slot:'2026-11-20T11:00:00Z'}, false, now),
    {value:'Сегодня, 12:00',tone:'neutral'});
  assert.equal(homeSlot({due_at:'2026-11-21T06:00:00Z'}, {}, false, now)?.value, '21 ноября, 09:00');
});

test('no ordinary slot is promised when the guard waits or publishing is paused', () => {
  const s = {next_slot:'2026-11-20T09:00:00Z'};
  assert.equal(homeSlot({}, s, true, now)?.value, 'Автопубликации ждут');
  assert.equal(homeSlot({}, {...s, paused:true}, false, now)?.value, 'На паузе');
  assert.equal(homeSlot({}, {next_slot:'invalid'}, false, now), null);
});
