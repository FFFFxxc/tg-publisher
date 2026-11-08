import test from 'node:test';
import assert from 'node:assert/strict';
import { nativeScheduleNotice } from '../src/lib/nativeSchedule.ts';

test('older backend and disabled guard render no false warning', () => {
  assert.equal(nativeScheduleNotice(), null);
  assert.equal(nativeScheduleNotice({enabled:false}), null);
});
test('whole-day native queue explains priority and no catch-up burst', () => {
  const n=nativeScheduleNotice({enabled:true,blocked:true,reason:'native_queue',scheduled_posts:24});
  assert.match(n.title,/24/);assert.equal(n.waiting,true);assert.equal(n.tone,'warning');
  assert.match(n.detail,/следующего свободного слота/);
});
test('quiet interval is configurable and readable', () => {
  const n=nativeScheduleNotice({enabled:true,blocked:true,reason:'quiet_period',quiet_seconds:600});
  assert.match(n.detail,/10 мин/);assert.equal(n.waiting,true);
});
test('RPC error is shown as waiting, never as an empty queue', () => {
  const n=nativeScheduleNotice({enabled:true,blocked:true,reason:'check_failed'});
  assert.match(n.title,/недоступна/);assert.equal(n.tone,'warning');
});
test('restart and initial check remain visibly pending', () => {
  for(const reason of ['not_checked','history_overflow']){
    assert.equal(nativeScheduleNotice({enabled:true,blocked:true,reason}).waiting,true);
  }
});
test('queue deletion does not promise immediate publication', () => {
  const n=nativeScheduleNotice({enabled:true,blocked:false,reason:'clear',waiting_for_slot:true});
  assert.match(n.title,/следующий слот/);assert.equal(n.waiting,true);
});
test('clear state reports protection enabled without pausing the bot', () => {
  const n=nativeScheduleNotice({enabled:true,blocked:false,reason:'clear'});
  assert.equal(n.waiting,false);assert.equal(n.tone,'success');
});
