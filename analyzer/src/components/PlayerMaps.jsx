import { useEffect, useRef } from 'react';
import { drawStadium } from './stadium.js';
import { drawDensity, HEAT_COLORS } from './heatmap-density.js';

export const MAP_LABELS = {
  heatmap: 'Movement heatmap', goals: 'Goals', assists: 'Assists',
  kicks: 'Kicks', passes: 'Passes', shots: 'Shots on goal',
};

function point(value) { return value && Number.isFinite(value.x) && Number.isFinite(value.y); }

function arrow(ctx, from, to) {
  const angle = Math.atan2(to.y - from.y, to.x - from.x);
  ctx.moveTo(from.x, from.y); ctx.lineTo(to.x, to.y);
  ctx.moveTo(to.x - 15 * Math.cos(angle - Math.PI / 6), to.y - 15 * Math.sin(angle - Math.PI / 6));
  ctx.lineTo(to.x, to.y);
  ctx.lineTo(to.x - 15 * Math.cos(angle + Math.PI / 6), to.y - 15 * Math.sin(angle + Math.PI / 6));
}

export function drawPlayerMap(canvas, stadium, player, statistic, color) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  drawStadium(ctx, stadium);
  if (statistic === 'heatmap') {
    drawDensity(ctx, stadium, player.maps?.heatmap || []);
    return;
  }
  ctx.fillStyle = ctx.strokeStyle = color;
  ctx.lineWidth = 4;
  for (const event of player.maps?.[statistic] || []) {
    if (statistic === 'kicks' || statistic === 'contacts') {
      if (!point(event)) continue;
      ctx.globalAlpha = 0.85;
      ctx.beginPath(); ctx.arc(event.x, event.y, 5, 0, Math.PI * 2); ctx.fill();
    } else if (point(event.from) && point(event.to)) {
      ctx.globalAlpha = 0.85;
      ctx.beginPath();
      if (point(event.via)) {
        ctx.strokeStyle = `color-mix(in srgb, ${color} 65%, white)`;
        ctx.moveTo(event.from.x, event.from.y); ctx.lineTo(event.via.x, event.via.y);
        ctx.stroke();
        ctx.beginPath();
        ctx.strokeStyle = color;
        arrow(ctx, event.via, event.to);
      } else {
        ctx.strokeStyle = color;
        arrow(ctx, event.from, event.to);
      }
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
}

export default function PlayerMaps({ game, player, statistic, onStatistic, labels = MAP_LABELS, embedded = false, hideStatistic = false }) {
  const canvas = useRef(null);
  useEffect(() => {
    if (!player) return;
    const color = getComputedStyle(canvas.current).getPropertyValue(player.team === 'red' ? '--color-error' : '--color-info').trim() || (player.team === 'red' ? '#ef929a' : '#8bb6ff');
    drawPlayerMap(canvas.current, game.stadium, player, statistic, color);
  }, [game.stadium, player, statistic]);
  if (!player) return null;
  const label = labels[statistic];
  const events = player.maps?.[statistic] || [];
  return <section aria-label="Player maps" className={embedded ? 'min-w-0' : 'min-w-0 border-t border-base-300 pt-5 @min-[80rem]:border-l @min-[80rem]:border-t-0 @min-[80rem]:pl-6 @min-[80rem]:pt-0'}>
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h3 className="text-sm font-semibold">{player.nick} · {label}</h3>
      {!hideStatistic && <div className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-2 text-xs text-base-content/60">Map statistic<select className="select select-sm w-44" value={statistic} onChange={event => onStatistic(event.target.value)}>{Object.entries(labels).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label>
      </div>}
    </div>
    <canvas ref={canvas} width="1000" height="500" role="img" aria-label={`${player.nick}: ${label}`} className="mx-auto block h-auto w-full max-w-3xl rounded-box" />
    {statistic === 'heatmap' && events.length > 0 && <div className="mx-auto mt-4 flex max-w-3xl items-center justify-end gap-2 text-[11px] text-base-content/60" aria-label="Relative occupancy: blue is low, red is high"><span>Less time</span><span className="h-2 w-32 rounded-full" style={{ background: `linear-gradient(to right, ${HEAT_COLORS.join(', ')})` }} /><span>More time</span></div>}
    {(!events.length || !['kicks', 'contacts'].includes(statistic)) && <p className="mt-3 text-xs text-base-content/55">{!player.maps ? 'Reopen the recording to generate spatial data.' : !events.length ? `No mapped ${label.toLowerCase()} for this player.` : statistic === 'heatmap' ? 'Warm colors highlight the busiest areas. Density is relative to this player’s movement during active play.' : ['assists', 'keyPasses'].includes(statistic) ? 'Lighter line: pass. Stronger arrow: shot.' : statistic === 'recoveries' ? 'Arrows connect the previous opponent’s control with where the ball was recovered.' : statistic === 'possessionLosses' ? 'Arrows connect the last controlled touch with the opponent’s recovery.' : 'Arrows show the direction of play.'}</p>}
  </section>;
}
