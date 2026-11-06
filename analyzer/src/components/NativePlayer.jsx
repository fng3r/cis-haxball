import { useEffect, useImperativeHandle, useRef, useState } from 'react';

export default function NativePlayer({ file, ref, onError, onStats, onClose }) {
  const frame = useRef(null);
  const pendingSeek = useRef(null);
  const ready = useRef(false);
  const [error, setError] = useState('');
  useImperativeHandle(ref, () => ({ seek(tick) {
    if (!ready.current) pendingSeek.current = tick;
    else frame.current?.contentWindow.postMessage({ type: 'seek', tick }, location.origin);
  } }), []);
  useEffect(() => {
    const receive = event => {
      if (event.source !== frame.current?.contentWindow || event.origin !== location.origin || event.data?.source !== 'haxball-native-player') return;
      if (event.data.type === 'ready') {
        ready.current = true;
        if (pendingSeek.current != null) {
          frame.current.contentWindow.postMessage({ type: 'seek', tick: pendingSeek.current }, location.origin);
          pendingSeek.current = null;
        }
      }
      if (event.data.type === 'error') { setError(event.data.message); onError(event.data.message); }
      if (event.data.type === 'stats') onStats();
      if (event.data.type === 'closed') onClose();
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [onError, onStats, onClose]);

  async function load() {
    ready.current = false;
    setError('');
    const target = frame.current?.contentWindow;
    try {
      const buffer = await file.arrayBuffer();
      if (frame.current?.contentWindow === target) target.postMessage({ type: 'open', buffer }, location.origin, [buffer]);
    } catch { setError('Could not read this replay file. Choose the recording again.'); }
  }

  return <div className="overflow-hidden rounded-box bg-neutral">
    {error && <p role="alert" className="p-4 text-sm text-neutral-content">{error}</p>}
    <iframe ref={frame} title="Original HaxBall replay player" src={`${import.meta.env.BASE_URL}player.html`} className="block h-[580px] w-full border-0" onLoad={load} allow="autoplay; fullscreen" />
  </div>;
}
