import { MAX_FILE_BYTES } from './engine/analyze.js';

export async function fetchMatchRecording(recording, signal) {
  const response = await fetch(recording.url, { signal: AbortSignal.any([signal, AbortSignal.timeout(30_000)]), credentials: 'omit', referrerPolicy: 'no-referrer' });
  if (!response.ok) throw new Error(`Recording download failed (HTTP ${response.status}).`);
  if (!response.body || Number(response.headers.get('content-length')) > MAX_FILE_BYTES) throw new Error('Recording exceeds 32 MiB.');
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_FILE_BYTES) throw new Error('Recording exceeds 32 MiB.');
      chunks.push(value);
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
  const file = new File(chunks, recording.name, { type: 'application/octet-stream' });
  const header = await file.slice(0, 12).arrayBuffer();
  if (header.byteLength < 12 || new DataView(header).getUint32(0) !== 0x48425232) throw new Error('The recording is not HBR2 data.');
  if (recording.sha256) {
    const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
    const hash = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
    if (hash !== recording.sha256) throw new Error('This recording has changed since Django analyzed it. Refresh its statistics before assigning teams.');
  }
  return file;
}

export function contextURL(href = window.location.href) {
  const value = new URL(href).searchParams.get('context');
  if (!value) return null;
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('Invalid match context URL.');
  return url;
}

export async function fetchMatchContext(url, signal) {
  const response = await fetch(url, { signal: AbortSignal.any([signal, AbortSignal.timeout(20_000)]), credentials: 'omit', referrerPolicy: 'no-referrer' });
  if (response.status === 409) throw new Error('Django has not prepared this match yet. Retry after its statistics have been processed.');
  if (!response.ok) throw new Error(`Match context unavailable (HTTP ${response.status}).`);
  const reader = response.body?.getReader();
  if (!reader) throw new Error('Empty match context response.');
  let length = 0;
  const chunks = [];
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > 1024 * 1024) throw new Error('Match context exceeds the size limit.');
      chunks.push(value);
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  const context = JSON.parse(new TextDecoder().decode(bytes));
  if (context.schemaVersion !== 2 || !context.match || !context.teams?.home || !context.teams?.away
    || !Array.isArray(context.recordings) || context.recordings.length > 128
    || !Array.isArray(context.parts) || context.parts.length > 2048) throw new Error('Unsupported match manifest.');
  function absolute(value) {
    const resolved = new URL(value, url);
    if (!['http:', 'https:'].includes(resolved.protocol) || resolved.username || resolved.password) throw new Error('Invalid manifest URL.');
    return resolved.href;
  }
  context.match.url = absolute(context.match.url);
  for (const team of Object.values(context.teams)) if (team.logo) team.logo = absolute(team.logo);
  const ids = new Set();
  for (const recording of context.recordings) {
    if (!Number.isInteger(recording.id) || ids.has(recording.id)) throw new Error('Invalid recording identity.');
    ids.add(recording.id);
    recording.url = absolute(recording.url);
    if (new URL(recording.url).origin !== new URL(url).origin) throw new Error('Recordings must come from the manifest origin.');
  }
  const partIds = new Set();
  for (const part of context.parts) {
    if (!Number.isInteger(part.id) || partIds.has(part.id) || !ids.has(part.recordingId)
      || !Number.isInteger(part.gameId) || !Number.isInteger(part.order)
      || typeof part.included !== 'boolean' || typeof part.redIsHome !== 'boolean') throw new Error('Invalid match part.');
    partIds.add(part.id);
  }
  context.parts.sort((a, b) => a.order - b.order || a.id - b.id);
  return context;
}
