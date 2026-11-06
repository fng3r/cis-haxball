import { useEffect, useImperativeHandle, useRef, useState } from 'react';
import { Clapperboard, RotateCcw, TriangleAlert } from 'lucide-react';
import { mountReplayHotkeys } from '../player/hotkeys.js';

export default function NativePlayer({ file, games, ref, focusMode = false, onExitFocus, onToggleFocus, onError, onStats, onClose, onGoal, onGame }) {
  const frame = useRef(null);
  const toggleFocus = useRef(onToggleFocus);
  toggleFocus.current = onToggleFocus;
  const pendingSeek = useRef(null);
  const ready = useRef(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  function sendSeek(type, tick) {
    if (!ready.current) pendingSeek.current = { type, tick };
    else frame.current?.contentWindow.postMessage({ type, tick }, location.origin);
  }
  function sendGoals() {
    frame.current?.contentWindow.postMessage({ type: 'goals', ticks: (games || []).flatMap(game => game.goals.map(goal => goal.tick)), starts: (games || []).map(game => game.startTick || 0) }, location.origin);
  }
  useImperativeHandle(ref, () => ({ seek: tick => sendSeek('seek', tick), seekGoal: tick => sendSeek('seek-goal', tick) }), []);
  useEffect(() => { if (ready.current) sendGoals(); }, [games]);
  useEffect(() => {
    const receive = event => {
      if (event.source !== frame.current?.contentWindow || event.origin !== location.origin || event.data?.source !== 'haxball-native-player') return;
      if (event.data.type === 'ready') {
        ready.current = true;
        setLoading(false); setError('');
        sendGoals();
        frame.current.contentWindow.postMessage({ type: 'focus-mode', enabled: focusMode }, location.origin);
        if (pendingSeek.current != null) {
          frame.current.contentWindow.postMessage(pendingSeek.current, location.origin);
          pendingSeek.current = null;
        }
      }
      if (event.data.type === 'error') { ready.current = false; setLoading(false); setError(event.data.message); onError(event.data.message); }
      if (event.data.type === 'toggle-focus') onToggleFocus?.();
      if (event.data.type === 'exit-focus') onExitFocus?.();
      if (event.data.type === 'stats') onStats();
      if (event.data.type === 'closed') onClose();
      if (event.data.type === 'goal') onGoal?.(event.data.message);
      if (event.data.type === 'game') onGame?.(event.data.message);
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [games, onError, onStats, onClose, onGoal, onGame, focusMode, onExitFocus, onToggleFocus]);

  useEffect(() => mountReplayHotkeys(window, action => {
    if (action === 'toggle-focus') { toggleFocus.current?.(); return; }
    if (!ready.current) return false;
    frame.current?.contentWindow.postMessage({ type: 'hotkey', action }, location.origin);
  }), []);

  useEffect(() => {
    if (ready.current) frame.current?.contentWindow.postMessage({ type: 'focus-mode', enabled: focusMode }, location.origin);
  }, [focusMode]);

  useEffect(() => {
    if (!loading) return;
    const timer = setTimeout(() => {
      ready.current = false; setLoading(false);
      setError('The player took too long to load. Try loading the replay again.');
    }, 45_000);
    return () => clearTimeout(timer);
  }, [loading, attempt]);

  function retry() {
    ready.current = false; setError(''); onError(''); setLoading(true); setAttempt(value => value + 1);
  }
  async function load() {
    ready.current = false;
    setError(''); setLoading(true);
    const target = frame.current?.contentWindow;
    try {
      const buffer = await file.arrayBuffer();
      if (frame.current?.contentWindow === target) target.postMessage({ type: 'open', buffer }, location.origin, [buffer]);
    } catch {
      if (frame.current?.contentWindow === target) { setLoading(false); setError('Could not read this replay file. Choose the recording again.'); }
    }
  }

  return <div className={`relative overflow-hidden rounded-box bg-neutral ${focusMode ? 'h-full' : ''}`} aria-busy={loading}>
    <iframe key={attempt} ref={frame} title="Original HaxBall replay player" src={`${import.meta.env.BASE_URL}player.html`} className={`block w-full border-0 ${focusMode ? 'h-full' : 'h-[max(420px,calc(100dvh-16rem))]'} ${loading || error ? 'pointer-events-none opacity-0' : ''}`} aria-hidden={loading || Boolean(error)} tabIndex={loading || error ? -1 : 0} onLoad={load} allow="autoplay; fullscreen" />
    {(loading || error) && <div className="absolute inset-0 flex flex-col items-center justify-center bg-base-200 p-6 text-center text-base-content">
      <div className="mb-6 flex size-20 items-center justify-center rounded-box border border-base-300 bg-base-100 shadow-sm">
        {error ? <TriangleAlert className="size-8 text-error" aria-hidden="true" /> : <Clapperboard className="size-8 text-primary" aria-hidden="true" />}
      </div>
      {error ? <>
        <h3 className="text-lg font-semibold">Couldn’t open the replay</h3>
        <p role="alert" className="mt-2 max-w-sm text-sm text-base-content/60">{error}</p>
        <button className="btn btn-sm mt-5" onClick={retry}><RotateCcw className="size-4" aria-hidden="true" />Retry player</button>
      </> : <div role="status" className="flex w-full max-w-md flex-col items-center">
        <h3 className="text-lg font-semibold">Preparing your replay</h3>
        <p className="mt-2 max-w-full truncate text-sm text-base-content/55" title={file.name}>{file.name}</p>
        <span className="loading loading-spinner loading-md mt-6 text-primary motion-reduce:animate-none" aria-hidden="true" />
        <p className="mt-3 text-xs text-base-content/45">Loading the player and recording…</p>
      </div>}
    </div>}
  </div>;
}
