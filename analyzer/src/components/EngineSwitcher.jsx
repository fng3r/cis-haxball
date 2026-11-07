import { changeEngine } from '../engine-selection.js';
import { isEngineV2Enabled } from '../feature-flags.js';

export default function EngineSwitcher({ engine }) {
  if (!isEngineV2Enabled()) return null;
  return <label className="flex items-center gap-2 text-xs text-base-content/60">
    <span>Engine</span>
    <select className="select select-sm w-36" aria-label="Analysis engine" title="Changing engine reloads the page and clears loaded recordings." value={engine} onChange={event => changeEngine(event.target.value)}>
      <option value="legacy">Original</option>
      <option value="v2">Engine v2</option>
    </select>
  </label>;
}
