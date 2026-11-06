import { useState } from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';
import ThirdsMap from './ThirdsMap.jsx';
import PlayerMaps from './PlayerMaps.jsx';

export const V2_MAP_LABELS = { heatmap: 'Movement heatmap', goals: 'Goals', assists: 'Assists', kicks: 'Kicks', contacts: 'Contacts', transfers: 'Transfers', received: 'Receptions', turnovers: 'Turnovers' };
const number = (value, digits = 0) => Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: digits }) : '—';
const duration = ticks => `${Math.floor(ticks / 3600)}:${String(Math.floor(ticks / 60) % 60).padStart(2, '0')}`;
const percent = (value, total) => `${total ? Math.round(value / total * 100) : 0}%`;
function TeamMetric({ label, red, blue, digits = 0 }) {
  return <div className="grid grid-cols-[minmax(3rem,1fr)_minmax(0,2fr)_minmax(3rem,1fr)] items-center gap-3 border-b border-base-300/60 py-3 text-sm">
    <span className="font-mono font-semibold text-error">{number(red, digits)}</span>
    <span className="text-center text-base-content/65">{label}</span>
    <span className="text-right font-mono font-semibold text-info">{number(blue, digits)}</span>
  </div>;
}
export function V2Overview({ game }) {
  const { red, blue } = game.teams;
  const redGoal = game.stadium.goals.find(goal => goal.team === 'red');
  const blueGoal = game.stadium.goals.find(goal => goal.team === 'blue');
  const pitchAligned = redGoal && blueGoal && redGoal.p0[0] < blueGoal.p0[0]
    && Math.abs((redGoal.p0[1] + redGoal.p1[1]) - (blueGoal.p0[1] + blueGoal.p1[1])) < 0.001;
  const buckets = [['red', 'Red in reach', 'bg-error/65'], ['blue', 'Blue in reach', 'bg-info/65'], ['contested', 'Both teams', 'bg-warning/65'], ['loose', 'Neither team', 'bg-base-content/20']];
  return <div className="space-y-6">
    <div className="stats stats-vertical w-full border border-base-300 bg-base-200 sm:stats-horizontal">
      {[['Active play', duration(game.activeTicks), 'Excludes pauses and resets'], ['Loose ball', percent(game.proximityTicks.loose, game.activeTicks), 'Neither team within reach'], ['Contested ball', percent(game.proximityTicks.contested, game.activeTicks), 'Both teams within reach']].map(([title, value, description]) => <div key={title} className="stat min-w-0">
        <div className="stat-title text-xs">{title}</div><div className="stat-value font-mono text-2xl">{value}</div><div className="stat-desc mt-1 text-xs">{description}</div>
      </div>)}
    </div>
    <div className="grid gap-8 xl:grid-cols-2">
      <section aria-label="Team ball actions">
        <div className="mb-1 flex justify-between text-xs font-semibold"><span className="text-error">Red team</span><h3 className="text-base-content">Ball actions</h3><span className="text-info">Blue team</span></div>
        {[['kicks', 'Successful kicks'], ['contacts', 'Contact episodes'], ['transfers', 'Observed transfers'], ['progressiveTransfers', 'Progressive transfers'], ['turnovers', 'Turnovers']].map(([key, label]) => <TeamMetric key={key} label={label} red={red[key]} blue={blue[key]} />)}
        <p className="mt-3 text-xs leading-relaxed text-base-content/55">Transfers and turnovers follow the next distinct ball interaction after a kick. They do not establish pass intent or controlled possession.</p>
      </section>
      <section aria-label="Ball territory" className="min-w-0 xl:border-l xl:border-base-300 xl:pl-8">
        <h3 className="mb-4 text-sm font-semibold">Ball territory</h3>
        {game.territoryAvailable ? (pitchAligned ? <ThirdsMap game={game} /> : <div><p className="mb-3 text-xs text-base-content/55">Goal-axis thirds · nonstandard pitch orientation</p><dl className="grid grid-cols-3 gap-2">{['Red third', 'Middle', 'Blue third'].map((label, index) => <div key={label} className="rounded-field bg-base-200 p-4 text-center"><dt className="text-xs text-base-content/60">{label}</dt><dd className="mt-2 font-mono text-xl">{percent(game.thirds[index], game.activeTicks)}</dd></div>)}</dl></div>) : <p className="py-8 text-sm text-base-content/55">Territory is unavailable without two usable goals.</p>}
        <p className="mt-3 text-xs text-base-content/55">Active ball time in three equal pitch regions.</p>
      </section>
      <section aria-label="Ball proximity">
        <h3 className="mb-4 text-sm font-semibold">Ball proximity</h3>
        <div className="flex h-3 overflow-hidden rounded-full" aria-hidden="true">{buckets.map(([key, , color]) => <div key={key} className={color} style={{ width: `${game.activeTicks ? game.proximityTicks[key] / game.activeTicks * 100 : 0}%` }} />)}</div>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">{buckets.map(([key, label, color]) => <div key={key} className="flex items-center gap-2"><span className={`size-2 rounded-full ${color}`} /><dt className="text-base-content/65">{label}</dt><dd className="ml-auto font-mono">{percent(game.proximityTicks[key], game.activeTicks)}</dd></div>)}</dl>
        <p className="mt-3 text-xs text-base-content/55">Reach is player radius + ball radius + 4 units. This measures proximity, not possession.</p>
      </section>
      <section aria-label="Team movement" className="xl:border-l xl:border-base-300 xl:pl-8">
        <h3 className="mb-1 text-sm font-semibold">Team movement</h3>
        <TeamMetric label="Distance travelled" red={red.distance} blue={blue.distance} />
        <TeamMetric label="Average width" red={red.averageWidth} blue={blue.averageWidth} digits={1} />
        <TeamMetric label="Average depth" red={red.averageDepth} blue={blue.averageDepth} digits={1} />
        <p className="mt-3 text-xs text-base-content/55">World units during active play. Team shape includes every on-field player.</p>
      </section>
    </div>
  </div>;
}

export function V2Players({ game, selectedPlayer, onSelect, mapStatistic, onStatistic }) {
  const [sort, setSort] = useState(null);
  const player = game.players.find(p => p.id === selectedPlayer) || game.players.find(p => p.team === 'red') || game.players[0];
  const players = [...game.players].sort((a, b) => sort
    ? (a[sort.key] - b[sort.key]) * (sort.direction === 'asc' ? 1 : -1) || a.nick.localeCompare(b.nick)
    : Number(a.team === 'blue') - Number(b.team === 'blue'));
  function show(item, statistic = 'heatmap') { onSelect(item.id); onStatistic(statistic); }
  function cycle(key) { setSort(current => current?.key !== key ? { key, direction: 'desc' } : current.direction === 'desc' ? { key, direction: 'asc' } : null); }
  const columns = [['goals', 'Goals'], ['assists', 'Assists'], ['kicks', 'Kicks'], ['transfers', 'Transfers'], ['received', 'Received'], ['turnovers', 'Turnovers'], ['distance', 'Distance'], ['activeTicks', 'Played']];
  return <div className="@container">
    <div className="grid items-start gap-6 @min-[80rem]:grid-cols-2">
      <div className="min-w-0">
        <div className="overflow-x-auto"><table className="table table-sm">
          <caption className="sr-only">V2 player statistics. Click a row for its heatmap or a statistic for its event map.</caption>
          <thead><tr><th className="min-w-40">Player</th>{columns.map(([key, label]) => <th key={key} className="text-right" aria-sort={sort?.key === key ? (sort.direction === 'asc' ? 'ascending' : 'descending') : undefined}><button className="btn btn-ghost btn-xs whitespace-nowrap" title={key === 'turnovers' ? 'A kick followed by an opponent’s next distinct ball interaction.' : key === 'transfers' ? 'A kick followed by a teammate’s next distinct ball interaction.' : undefined} onClick={() => cycle(key)}>{label}{sort?.key === key && (sort.direction === 'asc' ? <ArrowUp className="size-3" aria-hidden="true" /> : <ArrowDown className="size-3" aria-hidden="true" />)}</button></th>)}</tr></thead>
          <tbody>{players.map(item => <tr key={item.id} onClick={() => show(item)} className={`cursor-pointer transition-colors ${player?.id === item.id ? 'bg-base-200 hover:bg-base-300/60' : 'hover:bg-base-200/70'}`}>
            <th><button className="flex items-center gap-3 rounded-field py-2 text-left focus-visible:outline-2" aria-pressed={player?.id === item.id}><span className={`size-2 shrink-0 rounded-full ${item.team === 'red' ? 'bg-error' : 'bg-info'}`} />{item.nick}</button></th>
            {columns.map(([key, label]) => <td key={key} className="text-right font-mono">{key === 'activeTicks' ? <span className="px-2">{duration(item.activeTicks)}</span> : key === 'distance' ? <span className="px-2">{number(item.distance)}</span> : <button className="btn btn-ghost btn-xs font-mono" aria-label={`${label} map for ${item.nick}`} aria-pressed={player?.id === item.id && mapStatistic === key} onClick={event => { event.stopPropagation(); show(item, key); }}>{item[key]}</button>}</td>)}
          </tr>)}</tbody>
        </table></div>
        <p className="mt-4 text-xs leading-relaxed text-base-content/55">Click a row or statistic to select its map. Distance is in world units; played time is active play. Goal and assist credit uses recent ball interactions.</p>
      </div>
      <div className="min-w-0">
        <PlayerMaps game={game} player={player} statistic={mapStatistic} onStatistic={onStatistic} labels={V2_MAP_LABELS} />
        {player && <dl aria-label="Selected player movement and involvement" className="@min-[80rem]:ml-6 mt-5 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-base-300 pt-4 text-xs">{[
          ['Contacts', number(player.contacts)], ['Progressive transfers', number(player.progressiveTransfers)], ['Distance', `${number(player.distance)} units`], ['Average speed', `${number(player.averageSpeed, 1)} units/s`], ['Peak speed', `${number(player.peakSpeed, 1)} units/s`], ['On-field goal difference', number(player.onFieldGoalDifference)],
        ].map(([label, value]) => <div key={label} className="flex items-center justify-between gap-2"><dt className="text-base-content/60">{label}</dt><dd className="font-mono">{value}</dd></div>)}</dl>}
      </div>
    </div>
  </div>;
}
