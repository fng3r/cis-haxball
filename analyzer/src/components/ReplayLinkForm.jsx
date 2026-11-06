import { useEffect, useRef, useState } from 'react';
import { fetchThehaxReplay } from '../external-replay.js';

export default function ReplayLinkForm({ onFiles }) {
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef(null);
  useEffect(() => () => request.current?.abort(), []);
  async function submit(event) {
    event.preventDefault();
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError('');
    try {
      const file = await fetchThehaxReplay(url, { signal: controller.signal });
      if (!controller.signal.aborted) { onFiles([file]); setUrl(''); }
    } catch (error) {
      if (!controller.signal.aborted) setError(error.message);
    } finally {
      if (request.current === controller) { request.current = null; setBusy(false); }
    }
  }
  return <form onSubmit={submit} className="space-y-3 rounded-box border border-base-300 p-4" aria-label="Open replay link">
    <label className="block text-xs font-semibold" htmlFor="replay-url">Replay link</label>
    <input id="replay-url" type="url" required value={url} onChange={event => setUrl(event.target.value)} placeholder="https://replay.thehax.pl/…" className="input input-sm w-full" disabled={busy} />
    <p className="text-[11px] text-base-content/55">thehax.pl replay and forum links</p>
    {error && <p role="alert" className="text-xs text-error">{error}</p>}
    {busy ? <div className="flex items-center justify-between gap-2"><span role="status" className="text-xs text-base-content/60">Downloading replay…</span><button type="button" className="btn btn-xs" onClick={() => request.current?.abort()}>Cancel download</button></div>
      : <button type="submit" className="btn btn-sm w-full">Analyze link</button>}
  </form>;
}
