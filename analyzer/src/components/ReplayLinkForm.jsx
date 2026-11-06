import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchThehaxReplay } from '../external-replay.js';

export default function ReplayLinkForm({ onFiles }) {
  const [urls, setUrls] = useState('');
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
    const links = [...new Set(urls.trim().split(/\s+/).filter(Boolean))];
    if (!links.length) { setErrors(['Enter at least one replay link.']); return; }
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setErrors([]);
    const failures = [], remaining = new Set(links);
    try {
      for (const [index, link] of links.entries()) {
        if (controller.signal.aborted) return;
        setProgress(`Downloading replay ${index + 1} of ${links.length}…`);
        try {
          const file = await fetchThehaxReplay(link, { signal: controller.signal });
          if (controller.signal.aborted) return;
          onFiles([file]);
          remaining.delete(link);
          setUrls([...remaining].join('\n'));
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
    <button type="button" className="btn btn-sm w-full" onClick={() => { setErrors([]); dialog.current.showModal(); }}>Use replay links</button>
    {createPortal(<dialog ref={dialog} className="modal" aria-labelledby="replay-links-title" onCancel={stop} onClose={stop}>
      <div className="modal-box">
        <h2 id="replay-links-title" className="text-lg font-semibold">Analyze replay links</h2>
        <p id="replay-links-help" className="mt-2 text-sm text-base-content/60">Paste thehax.pl replay or forum links, one per line.</p>
        <form onSubmit={submit} className="mt-5" aria-label="Open replay links">
          <label htmlFor="replay-urls" className="mb-2 block text-sm font-semibold">Replay links</label>
          <textarea id="replay-urls" autoFocus rows={6} value={urls} onChange={event => setUrls(event.target.value)} aria-describedby="replay-links-help" placeholder="https://replay.thehax.pl/…" className="textarea w-full" disabled={busy} />
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
