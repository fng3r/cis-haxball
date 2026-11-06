import { useEffect, useImperativeHandle, useRef, useState } from 'react';
import { mountReplayHotkeys } from '../player/hotkeys.js';

export default function NativePlayer({ file, games, ref, focusMode = false, onExitFocus, onError, onStats, onClose, onGoal, onGame }) {
  const frame = useRef(null);
  const pendingSeek = useRef(null);
  const ready = useRef(false);
  const [error, setError] = useState('');
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
        sendGoals();
        frame.current.contentWindow.postMessage({ type: 'focus-mode', enabled: focusMode }, location.origin);
        if (pendingSeek.current != null) {
          frame.current.contentWindow.postMessage(pendingSeek.current, location.origin);
          pendingSeek.current = null;
        }
      }
      if (event.data.type === 'error') { setError(event.data.message); onError(event.data.message); }
      if (event.data.type === 'exit-focus') onExitFocus?.();
      if (event.data.type === 'stats') onStats();
      if (event.data.type === 'closed') onClose();
      if (event.data.type === 'goal') onGoal?.(event.data.message);
      if (event.data.type === 'game') onGame?.(event.data.message);
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [games, onError, onStats, onClose, onGoal, onGame, focusMode, onExitFocus]);

  useEffect(() => mountReplayHotkeys(window, action => {
    if (!ready.current) return false;
    frame.current?.contentWindow.postMessage({ type: 'hotkey', action }, location.origin);
  }), []);

  useEffect(() => {
    if (ready.current) frame.current?.contentWindow.postMessage({ type: 'focus-mode', enabled: focusMode }, location.origin);
  }, [focusMode]);

  async function load() {
    ready.current = false;
    setError('');
    const target = frame.current?.contentWindow;
    try {
      const buffer = await file.arrayBuffer();
      if (frame.current?.contentWindow === target) target.postMessage({ type: 'open', buffer }, location.origin, [buffer]);
    } catch { setError('Could not read this replay file. Choose the recording again.'); }
  }

  return <div className={`overflow-hidden rounded-box bg-neutral ${focusMode ? 'h-full' : ''}`} >
    {error && <p role="alert" className="p-4 text-sm text-neutral-content">{error}</p>}
    <iframe ref={frame} title="Original HaxBall replay player" src={`${import.meta.env.BASE_URL}player.html`} className={`block w-full border-0 ${focusMode ? 'h-full' : 'h-[max(420px,calc(100dvh-16rem))]'}`}  onLoad={load} allow="autoplay; fullscreen" />
  </div>;
}
