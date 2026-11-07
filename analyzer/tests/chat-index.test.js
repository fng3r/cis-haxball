import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { inflateRaw } from 'pako';
import { afterAll, expect, it } from 'vitest';
import { captureChat, indexReplayChat } from '../src/player/chat-index.js';
import { replayCases } from './replay-fixtures.js';

// Exercise the pinned decoder without importing browser UI or adding a third
// production runtime. The temporary module is removed after the test process.
const original = await readFile(new URL('../legacy/src/game2.js', import.meta.url), 'utf8');
let source = original.slice(original.indexOf('var kicker, lastKicker')).replace(/export /g, '').replace(/u\.qp\(\)\s*$/, '');
const start = source.indexOf('        if (!match[match.length - 1].stadium) {');
const end = source.indexOf('        //console.log("coś",this.Hc)', start);
source = source.slice(0, start) + source.slice(end);
const directory = await mkdtemp(join(tmpdir(), 'chat-index-test-'));
const file = join(directory, 'runtime.mjs');
await writeFile(file, `export function replay(bytes, inflateRaw) { const pako = {inflateRaw}; const window = {performance:{now:()=>0}}; const loading={done:true};\n${source}\nkeepUpdating=false;kc.fj();const replay=new Jb(bytes,new fa,3);replay.isGameStart=action=>action instanceof Ma;return replay;}`);
const { replay: createReplay } = await import(pathToFileURL(file));
afterAll(() => rm(directory, { recursive: true, force: true }));

it.each(replayCases)('indexes chat identically to native physics playback: $file', async ({ file }) => {
  const bytes = Uint8Array.from(await readFile(new URL(`./fixtures/${file}`, import.meta.url)));
  const indexedReplay = createReplay(bytes, inflateRaw);
  const indexed = indexReplayChat(indexedReplay, indexedReplay.isGameStart);
  const reference = createReplay(bytes, inflateRaw);
  const played = captureChat(reference.T, () => reference.Y);
  while (reference.Y < reference.mf) {
    while (reference.gg && reference.hg === reference.Y) {
      reference.gg.apply(reference.T); reference.Dl();
    }
    reference.Y++; reference.T.C(1);
  }
  expect(indexed).toEqual(played);
  expect(indexed.some(e => e.type === 'chat')).toBe(true);
  expect(indexed.some(e => e.type === 'announcement')).toBe(true);
  expect(indexed.map(e => e.tick)).toEqual(indexed.map(e => e.tick).sort((a,b) => a-b));
  // No physics advancement: the native match clock remains at its initial value.
  expect(indexedReplay.Qb).toBe(0);
});
