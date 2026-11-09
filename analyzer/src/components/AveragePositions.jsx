import { useEffect, useRef } from 'react';
import { drawStadium } from './stadium.js';
import { TeamIdentity } from './MatchContext.jsx';

export function averagePosition(player) {
  let x = 0, y = 0, ticks = 0;
  for (const cell of player.maps?.heatmap || []) {
    if (!Number.isFinite(cell.x) || !Number.isFinite(cell.y) || !Number.isFinite(cell.ticks) || cell.ticks <= 0) continue;
    x += cell.x * cell.ticks; y += cell.y * cell.ticks; ticks += cell.ticks;
  }
  return ticks ? { x: x / ticks, y: y / ticks } : null;
}

function TeamPositions({ game, team, identity }) {
  const canvas = useRef(null);
  const players = game.players.filter(player => player.team === team).map(player => ({ player, position: averagePosition(player) })).filter(item => item.position);
  const teamName = identity?.name || (team === 'red' ? 'Red team' : 'Blue team');
  useEffect(() => {
    const ctx = canvas.current?.getContext('2d');
    if (ctx) drawStadium(ctx, game.stadium);
  }, [game.stadium, players.length]);
  return <figure className="min-w-0 space-y-4">
    <figcaption className={`text-sm font-semibold ${team === 'red' ? 'text-error' : 'text-info'}`}><TeamIdentity team={identity} fallback={teamName} logoClassName="size-5" /></figcaption>
    {players.length ? <div className="relative mx-auto max-w-3xl overflow-hidden rounded-box" role="img" aria-label={`${teamName} average positions: ${players.map(({ player }) => player.nick).join(', ')}`}>
      <canvas ref={canvas} width="1000" height="500" className="block h-auto w-full" aria-hidden="true" />
      <div className="absolute inset-0" aria-hidden="true">
        {players.map(({ player, position }) => <div key={player.id} title={player.nick} className="absolute flex -translate-x-1/2 -translate-y-2 flex-col items-center sm:-translate-y-2.5" style={{ left: `${(position.x + game.stadium.width) / (2 * game.stadium.width) * 100}%`, top: `${(position.y + game.stadium.height) / (2 * game.stadium.height) * 100}%` }}>
          <span className={`size-4 shrink-0 rounded-full border-2 border-base-100 shadow-sm sm:size-5 ${team === 'red' ? 'bg-error' : 'bg-info'}`} />
          <span className="mt-1 max-w-28 truncate rounded-field bg-base-100/90 px-1.5 py-0.5 text-[10px] font-semibold text-base-content shadow-sm sm:text-xs">{player.nick}</span>
        </div>)}
      </div>
    </div> : <p className="py-8 text-sm text-base-content/55">No movement data for this team.</p>}
  </figure>;
}

export default function AveragePositions({ game, redIdentity, blueIdentity }) {
  return <section aria-label="Average positions" className="@container mt-8 border-t border-base-300 pt-6">
    <h3 className="mb-2 text-sm font-semibold">Average positions</h3>
    <p className="mb-5 text-xs text-base-content/55">Each marker shows a player’s average location during play, including substitutes.</p>
    <div className="grid items-start gap-6 @min-[48rem]:grid-cols-2">
      <TeamPositions game={game} team="red" identity={redIdentity} />
      <TeamPositions game={game} team="blue" identity={blueIdentity} />
    </div>
  </section>;
}
