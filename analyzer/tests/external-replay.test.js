import { afterEach, expect, it, vi } from 'vitest';
import { fetchThehaxReplay, thehaxReplayId } from '../src/external-replay.js';
import { MAX_FILE_BYTES } from '../src/engine/analyze.js';

afterEach(() => vi.unstubAllGlobals());
const id = '7fa610525dbe630c8bd68dd55c266b4f';
it('resolves current, download, forum and wrapped links to the same replay', () => {
  const forum = `https://thehax.pl/forum/powtorki.php?nagranie=${id}`;
  for (const link of [`https://replay.thehax.pl/${id}`, `http://replay.thehax.pl/${id}/download/`, forum, `https://vk.com/away.php?to=${encodeURIComponent(forum)}`]) expect(thehaxReplayId(link)).toBe(id);
  for (const link of ['not a URL', 'https://evil.com/id', 'https://replay.thehax.pl.evil.com/id', 'https://replay.thehax.pl/', 'https://thehax.pl/forum/powtorki.php?nagranie=../bad', 'https://user@replay.thehax.pl/id', 'https://replay.thehax.pl:444/id']) expect(() => thehaxReplayId(link)).toThrow();
});
it('downloads a validated replay from the canonical host without credentials', async () => {
  const bytes = new Uint8Array(12); new DataView(bytes.buffer).setUint32(0, 0x48425232);
  const fetch = vi.fn(async () => new Response(bytes)); vi.stubGlobal('fetch', fetch);
  const file = await fetchThehaxReplay(`https://replay.thehax.pl/${id}`);
  expect(file.name).toBe(`thehax-${id}.hbr2`);
  expect(new Uint8Array(await file.arrayBuffer())).toEqual(bytes);
  expect(fetch).toHaveBeenCalledWith(`https://replay.thehax.pl/${id}/download`, expect.objectContaining({ mode: 'cors', credentials: 'omit', signal: expect.any(AbortSignal) }));
});
it('rejects HTTP failures, HTML responses and oversized declared or streamed downloads', async () => {
  for (const response of [new Response('missing', { status: 404 }), new Response('<html>not a replay</html>'), new Response('x', { headers: { 'content-length': String(MAX_FILE_BYTES + 1) } }), new Response(new Uint8Array(MAX_FILE_BYTES + 1))]) {
    vi.stubGlobal('fetch', vi.fn(async () => response));
    await expect(fetchThehaxReplay(`https://replay.thehax.pl/${id}`)).rejects.toThrow();
  }
});
it('explains browser network errors and preserves user cancellation', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
  await expect(fetchThehaxReplay(`https://replay.thehax.pl/${id}`)).rejects.toThrow('blocking browser requests');
  const controller = new AbortController(); controller.abort();
  vi.stubGlobal('fetch', vi.fn(async (_, options) => { options.signal.throwIfAborted(); }));
  await expect(fetchThehaxReplay(`https://replay.thehax.pl/${id}`, { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' });
});
