import { isEngineV2Enabled } from './feature-flags.js';

export function getEngine(href = window.location.href) {
  if (!isEngineV2Enabled()) return 'legacy';
  const parameter = new URL(href).searchParams.get('engine');
  if (['legacy', 'v2'].includes(parameter)) return parameter;
  try { return localStorage.getItem('replay-engine') === 'v2' ? 'v2' : 'legacy'; }
  catch { return 'legacy'; }
}
export function changeEngine(engine, { navigate = url => window.location.assign(url) } = {}) {
  if (engine === 'v2' && !isEngineV2Enabled()) return;
  if (!['legacy', 'v2'].includes(engine) || engine === getEngine()) return;
  try { localStorage.setItem('replay-engine', engine); } catch { /* URL persists the selection when storage is unavailable. */ }
  const url = new URL(window.location.href);
  url.searchParams.set('engine', engine);
  navigate(url.href);
}
