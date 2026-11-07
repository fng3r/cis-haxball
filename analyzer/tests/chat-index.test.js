import { readFile } from 'node:fs/promises';
import { inflateRaw } from 'pako';
import { afterAll, expect, it } from 'vitest';
import { captureChat } from '../src/player/chat-index.js';
import { prepareReplayCheckpoints, stepReplay } from '../src/player/checkpoints.js';
import { replayCases } from './replay-fixtures.js';
import { nativeReplayFixture } from './native-replay-fixture.js';
const runtime = await nativeReplayFixture();
afterAll(runtime.dispose);

it.each(replayCases)('indexes chat during checkpoint preparation: $file', async ({ file }) => {
  const bytes = Uint8Array.from(await readFile(new URL(`./fixtures/${file}`, import.meta.url)));
  const indexed = runtime.create(bytes, inflateRaw);
  const { chatEntries } = prepareReplayCheckpoints(indexed.replay, indexed.save);
  const { replay } = runtime.create(bytes, inflateRaw);
  const played = captureChat(replay.T, () => replay.Y);
  while (replay.Y < replay.mf) stepReplay(replay);
  expect(chatEntries).toEqual(played);
  expect(chatEntries.some(e => e.type === 'chat')).toBe(true);
  expect(chatEntries.some(e => e.type === 'announcement')).toBe(true);
  expect(chatEntries.map(e => e.tick)).toEqual(chatEntries.map(e => e.tick).sort((a,b) => a-b));
});
