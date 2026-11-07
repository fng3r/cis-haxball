import { MAX_FILE_BYTES } from './engine/analyze.js';

export function matchId(href = window.location.href) {
  const value = new URL(href).searchParams.get('match');
  if (value === null) return null;
  if (!/^[1-9]\d{0,9}$/.test(value)) throw new Error('Invalid match reference.');
  return value;
}

export function inferMapping(game, context) {
  if (!game || !context) return null;
  const votes = new Set();
  for (const player of game.players) {
    if (!player.playedTicks) continue;
    const nick = player.nick.trim().toLocaleLowerCase();
    const home = context.rosters.home.includes(nick), away = context.rosters.away.includes(nick);
    if (home === away) continue;
    votes.add(home === (player.team === 'red'));
  }
  return votes.size === 1 ? [...votes][0] : null;
}

export async function fetchMatchRecording(recording, signal) {
  const response = await fetch(recording.url, { signal: AbortSignal.any([signal, AbortSignal.timeout(30_000)]), credentials: 'same-origin' });
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

export async function saveMapping(recording, game, redIsHome) {
  const csrf = document.cookie.split('; ').find(item => item.startsWith('csrftoken='))?.slice(10);
  const response = await fetch(recording.mappingUrl, {
    method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf || '' },
    body: JSON.stringify({ game, redIsHome }),
  });
  if (!response.ok) throw new Error(`Could not save the team mapping (HTTP ${response.status}). Import this match in Django first, then retry.`);
}
