// @vitest-environment jsdom
import { expect, it, vi } from 'vitest';
import { chatEndAt, mountChatSync } from '../src/player/chat-sync.js';
import { mountGameSync } from '../src/player/game-sync.js';

function setup(entries) {
  const log = document.createElement('div');
  const g = document.createElement('div');
  const reset = document.createElement('button'); reset.dataset.hook = 'reset'; g.append(reset);
  const controls = { g, C: vi.fn() };
  const replay = { Qb: 0, Fd: -1, mh: 1, ui() { this.Qb = 0; }, er(tick) { this.Fd = tick; if (tick < this.Qb) this.ui(); } };
  reset.onclick = () => replay.ui();
  mountGameSync(controls, replay, () => {});
  const chat = { dc: log, ba: () => { throw Error('native append'); }, Gb: () => {}, pp: () => {} };
  mountChatSync(controls, replay, chat, entries);
  return { log, controls, replay, chat, reset };
}
const entries = [
  { tick: 10, type: 'chat', text: 'A: first' },
  { tick: 20, type: 'announcement', text: '<b>announcement</b>', color: 0x123456, style: 4 },
  { tick: 20, type: 'notice', text: 'B has joined' },
  { tick: 30, type: 'chat', text: 'B: last' },
];
it('finds all messages at a timestamp including same-tick messages and boundaries', () => {
  expect(chatEndAt([], 10)).toBe(0);
  expect([0, 10, 19, 20, 100].map(tick => chatEndAt(entries, tick))).toEqual([0,1,1,3,4]);
});
it('populates forward/backward seeks immediately while paused and avoids duplicates on replay', () => {
  const { log, controls, replay, chat, reset } = setup(entries);
  expect(log.children.length).toBe(0);
  replay.Qb = 20; controls.C();
  expect(log.children.length).toBe(3);
  const firstNode = log.firstChild;
  controls.C(); expect(log.firstChild).toBe(firstNode);
  chat.ba('A: first'); chat.Gb('duplicate notice'); chat.pp('duplicate announcement');
  expect(log.children.length).toBe(3);
  replay.er(10); expect(log.textContent).toBe('A: first');
  // Intermediate simulation ticks while seeking must not replace destination chat.
  replay.Qb = 5; controls.C(); expect(log.textContent).toBe('A: first');
  replay.Fd = -1; replay.Qb = 20; controls.C(); expect(log.children.length).toBe(3);
  replay.er(30); expect(log.children.length).toBe(4);
  reset.click(); expect(log.children.length).toBe(0);
  replay.Qb = 30; controls.C(); expect(log.children.length).toBe(4);
});
it('retains announcement styles and renders message content as text', () => {
  const { log, replay } = setup(entries); replay.er(20);
  const announcement = log.children[1];
  expect(announcement.textContent).toBe('<b>announcement</b>');
  expect(announcement.querySelector('b')).toBeNull();
  expect(announcement.style.fontWeight).toBe('bold');
  expect(announcement.style.fontSize).toBe('12px');
  expect(announcement.style.color).toBe('rgb(18, 52, 86)');
  expect(log.children[2].className).toBe('notice');
});
it('bounds chat to the most recent 100 rows across large jumps', () => {
  const { log, replay, controls } = setup(Array.from({length: 250}, (_,tick) => ({tick, type:'chat', text:String(tick)})));
  replay.er(249); expect(log.children.length).toBe(100); expect(log.firstChild.textContent).toBe('150');
  replay.er(5); expect(log.children.length).toBe(6);
  replay.Fd = -1; replay.Qb = 249; controls.C(); expect(log.children.length).toBe(100);
});
