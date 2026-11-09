import { useState } from 'react';
import PlayerMaps, { MAP_LABELS } from './PlayerMaps.jsx';

export default function PlayerComparison({ game, selectedPlayer, statistic, onStatistic, labels = MAP_LABELS, redIdentity, blueIdentity }) {
  const first = game.players.find(player => player.id === selectedPlayer) || game.players.find(player => player.team === 'red') || game.players[0];
  const [leftId, setLeftId] = useState(first?.id);
  const [rightId, setRightId] = useState(() => game.players.find(player => player.team !== first?.team)?.id || game.players.find(player => player.id !== first?.id)?.id);
  const left = game.players.find(player => player.id === leftId) || first;
  const right = game.players.find(player => player.id === rightId && player.id !== left?.id) || game.players.find(player => player.id !== left?.id);
  const visibleStatistic = Object.hasOwn(labels, statistic) ? statistic : 'heatmap';
  const sides = [
    { label: 'Left player', player: left, other: right, select: setLeftId },
    { label: 'Right player', player: right, other: left, select: setRightId },
  ];
  return <section aria-label="Player comparison" className="@container space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="text-sm font-semibold">Compare players</h3>
      <label className="flex items-center gap-2 text-xs text-base-content/60">Map statistic
        <select className="select select-sm w-44" value={visibleStatistic} onChange={event => onStatistic(event.target.value)}>
          {Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
      </label>
    </div>
    <div className="grid items-start gap-6 @min-[48rem]:grid-cols-2">
      {sides.map(side => <div key={side.label} className="min-w-0 space-y-5">
        <label className="flex flex-col gap-2 text-xs text-base-content/60">{side.label}
          <select className="select select-sm w-full" value={side.player?.id || ''} onChange={event => side.select(event.target.value)}>
            {['red', 'blue'].map(team => <optgroup key={team} label={(team === 'red' ? redIdentity : blueIdentity)?.name || (team === 'red' ? 'Red team' : 'Blue team')}>
              {game.players.filter(player => player.team === team).map(player => <option key={player.id} value={player.id} disabled={player.id === side.other?.id}>{player.nick}</option>)}
            </optgroup>)}
          </select>
        </label>
        <PlayerMaps game={game} player={side.player} statistic={visibleStatistic} labels={labels} embedded hideStatistic />
      </div>)}
    </div>
  </section>;
}
