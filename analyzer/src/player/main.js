import { openNativeReplay, seekNativeReplay, setNativeGoals, setNativeGames, seekNativeGoal, replayHotkey } from './vendor-player.js';
import './player.scss';
import { mountReplayHotkeys } from './hotkeys.js';

mountReplayHotkeys(window, replayHotkey);

window.addEventListener('message', async event => {
  if (event.source !== parent || event.origin !== location.origin) return;
  if (event.data?.type === 'hotkey') replayHotkey(event.data.action);
  if (event.data?.type === 'seek') seekNativeReplay(event.data.tick);
  if (event.data?.type === 'seek-goal') seekNativeGoal(event.data.tick);
  if (event.data?.type === 'goals') {
    setNativeGoals(event.data.ticks);
    setNativeGames(event.data.starts || []);
  }
  if (event.data?.type !== 'open') return;
  try {
    await openNativeReplay(event.data.buffer);
    parent.postMessage({ source: 'haxball-native-player', type: 'ready' }, location.origin);
  } catch (error) {
    const message = error.message || 'Could not open this recording in the native player.';
    document.getElementById('status').textContent = message;
    parent.postMessage({ source: 'haxball-native-player', type: 'error', message }, location.origin);
  }
});
