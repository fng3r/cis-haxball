import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, Plus, X } from 'lucide-react';
import { fetchThehaxReplay } from '../external-replay.js';

export default function ReplayLinkForm({ onFiles }) {
  const [urls, setUrls] = useState([{ id: 0, value: '' }]);
  const nextId = useRef(1);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState([]);
  const [progress, setProgress] = useState('');
  const request = useRef(null), dialog = useRef(null);
  useEffect(() => () => request.current?.abort(), []);
  function stop() {
    request.current?.abort(); request.current = null; setBusy(false);
  }
  function close() { stop(); dialog.current.close(); }
  async function submit(event) {
    event.preventDefault();
    if (request.current) return;
    const links = [...new Set(urls.map(row => row.value.trim()).filter(Boolean))];
    if (!links.length) { setErrors(['Enter at least one replay link.']); return; }
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setErrors([]);
    const failures = [];
    let imported = false;
    try {
      for (const [index, link] of links.entries()) {
        if (controller.signal.aborted) return;
        setProgress(`Downloading replays: ${index + 1} of ${links.length}…`);
        try {
          const file = await fetchThehaxReplay(link, { signal: controller.signal });
          if (controller.signal.aborted) return;
          if (imported) onFiles([file], { selectFirst: false });
          else onFiles([file]);
          imported = true;
          setUrls(rows => {
            const remaining = rows.filter(row => row.value.trim() && row.value.trim() !== link);
            return remaining.length ? remaining : [{ id: nextId.current++, value: '' }];
          });
        } catch (error) {
          if (controller.signal.aborted) return;
          failures.push(`${link}: ${error.message}`);
        }
      }
      setErrors(failures);
      if (!failures.length) close();
    } finally {
      if (request.current === controller) { request.current = null; setBusy(false); }
    }
  }
  return <>
    <div className="divider my-3 text-[10px] text-base-content/45">OR</div>
    <button type="button" className="btn btn-sm w-full" onClick={() => { setErrors([]); dialog.current.showModal(); }}><Link className="size-4 shrink-0" aria-hidden="true" />Use replay links</button>
    {createPortal(<dialog ref={dialog} className="modal" aria-labelledby="replay-links-title" onCancel={stop} onClose={stop}>
      <div className="modal-box">
        <h2 id="replay-links-title" className="text-lg font-semibold">Analyze replay links</h2>
        <p id="replay-links-help" className="mt-2 text-sm text-base-content/60">Add thehax.pl replay or forum links below.</p>
        <form onSubmit={submit} className="mt-5" aria-label="Open replay links">
          <p className="mb-2 text-sm font-semibold">Replay links</p>
          <div className="space-y-3">{urls.map((row, index) => <div key={row.id} className="flex items-center gap-2">
            <label htmlFor={`replay-url-${row.id}`} className="sr-only">Replay link {index + 1}</label>
            <input id={`replay-url-${row.id}`} type="url" autoFocus={index === 0} value={row.value} onChange={event => setUrls(rows => rows.map(item => item.id === row.id ? { ...item, value: event.target.value } : item))} aria-describedby="replay-links-help" placeholder="https://replay.thehax.pl/…" className="input min-w-0 flex-1" disabled={busy} />
            <button type="button" className="btn btn-ghost btn-square shrink-0" aria-label={`Remove link ${index + 1}`} disabled={busy} onClick={() => setUrls(rows => {
              const remaining = rows.filter(item => item.id !== row.id);
              return remaining.length ? remaining : [{ id: nextId.current++, value: '' }];
            })}><X className="size-4" aria-hidden="true" /></button>
          </div>)}</div>
          <button type="button" className="btn btn-sm btn-ghost mt-3" disabled={busy} onClick={() => setUrls(rows => [...rows, { id: nextId.current++, value: '' }])}><Plus className="size-4" aria-hidden="true" />Add link</button>
          {errors.length > 0 && <div role="alert" className="mt-3 space-y-2 break-words text-sm text-error">{errors.map((error, index) => <p key={index}>{error}</p>)}</div>}
          {busy && <p role="status" className="mt-3 text-sm text-base-content/60">{progress}</p>}
          <div className="modal-action">
            <button type="button" className="btn" onClick={close}>{busy ? 'Cancel downloads' : 'Cancel'}</button>
            <button type="submit" className="btn btn-primary" disabled={busy}>Analyze</button>
          </div>
        </form>
      </div>
      <form method="dialog" className="modal-backdrop"><button aria-label="Close replay links">close</button></form>
    </dialog>, document.body)}
  </>;
}
