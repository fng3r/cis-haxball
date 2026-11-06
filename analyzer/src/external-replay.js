import { MAX_FILE_BYTES } from './engine/analyze.js';

export function thehaxReplayId(value, depth = 0) {
  if (depth > 3) throw new Error('Too many nested replay links.');
  let url;
  try { url = new URL(value.trim()); } catch { throw new Error('Enter a complete thehax.pl replay URL.'); }
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.port) throw new Error('Enter a supported thehax.pl replay URL.');
  let id;
  if (url.hostname === 'replay.thehax.pl') {
    const match = url.pathname.match(/^\/([^/]+)(?:\/download)?\/?$/);
    id = match?.[1];
  } else if (['thehax.pl', 'www.thehax.pl'].includes(url.hostname) && url.pathname === '/forum/powtorki.php') {
    id = url.searchParams.get('nagranie');
  } else if (['vk.com', 'www.vk.com'].includes(url.hostname) && url.pathname === '/away.php') {
    return thehaxReplayId(url.searchParams.get('to') || '', depth + 1);
  }
  if (!id || !/^[a-zA-Z0-9_-]{1,128}$/.test(id)) throw new Error('Use a replay.thehax.pl link or a thehax.pl forum replay link.');
  return id;
}

export async function fetchThehaxReplay(value, { signal } = {}) {
  const id = thehaxReplayId(value);
  const timeout = AbortSignal.timeout(20_000);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  let reader;
  try {
    const response = await fetch(`https://replay.thehax.pl/${id}/download`, {
      mode: 'cors', credentials: 'omit', referrerPolicy: 'no-referrer', signal: combined,
    });
    if (!response.ok) throw new Error(`The replay host returned HTTP ${response.status}. Check that the link is available.`);
    if (!response.body) throw new Error('The link did not return an HBR2 replay.');
    reader = response.body.getReader();
    if (Number(response.headers.get('content-length')) > MAX_FILE_BYTES) throw new Error('The replay exceeds the 32 MB file limit.');
    const chunks = [];
    let size = 0;
    for (;;) {
      const { done, value: chunk } = await reader.read();
      if (done) break;
      size += chunk.byteLength;
      if (size > MAX_FILE_BYTES) throw new Error('The replay exceeds the 32 MB file limit.');
      chunks.push(chunk);
    }
    const file = new File(chunks, `thehax-${id}.hbr2`, { type: 'application/octet-stream' });
    const header = await file.slice(0, 12).arrayBuffer();
    if (header.byteLength < 12 || new DataView(header).getUint32(0) !== 0x48425232) throw new Error('The link did not return an HBR2 replay. It may have expired or been removed.');
    return file;
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timeout.aborted) throw new Error('The replay download timed out after 20 seconds. Try again.');
    if (error instanceof TypeError) throw new Error('Could not download the replay. Check your connection; the host may be unavailable or blocking browser requests.');
    throw error;
  } finally {
    await reader?.cancel().catch(() => {});
    reader?.releaseLock();
  }
}
