import { openNativeReplay, seekNativeReplay, setNativeGoals, seekNativeGoal } from './vendor-player.js';
import './player.scss';

window.addEventListener('message', async event => {
  if (event.source !== parent || event.origin !== location.origin) return;
  if (event.data?.type === 'seek') seekNativeReplay(event.data.tick);
  if (event.data?.type === 'seek-goal') seekNativeGoal(event.data.tick);
  if (event.data?.type === 'goals') setNativeGoals(event.data.ticks);
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
