import { useState } from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';
import ThirdsMap from './ThirdsMap.jsx';
import PlayerMaps from './PlayerMaps.jsx';

export const V2_MAP_LABELS = {
  heatmap: 'Movement heatmap', goals: 'Goals', assists: 'Assists', ownGoals: 'Own goals', kicks: 'Kicks',
  shotsOnTarget: 'Shots on target', completedPasses: 'Completed passes', passesReceived: 'Passes received',
  progressivePasses: 'Progressive passes', keyPasses: 'Key passes', recoveries: 'Recoveries', possessionLosses: 'Possession losses',
};
const descriptions = {
  possessionTicks: 'Time credited to the team that last controlled the ball, including ball flight. Time before either team gains control is excluded from the percentages.',
  completedPasses: 'Kicks received by a teammate within 5 seconds, through a kick or settled control. Deflections alone do not complete a pass. Goal-bound shots are counted separately.',
  passesReceived: 'Completed passes received from a teammate, including receptions without another kick.',
  progressivePasses: 'Completed passes that bring the ball closer to the opposing goal by at least 10% of the pitch length.',
  shotsOnTarget: 'Kicks whose direct trajectory would reach the goal opening before slowing down. Allows for ball size; wall rebounds and gravity-driven trajectories are excluded.',
  keyPasses: 'Completed passes followed by the receiver’s shot on target within 8 seconds, without an opposing touch. Each pass receives at most one credit.',
  recoveries: 'Gaining control after the opposition had possession. A deflection alone does not count; the first touch after a restart does not count.',
  possessionLosses: 'Losing established possession to an opponent. Shots on target and restarts do not count as losses.',
};
const groups = {
  Attack: ['goals', 'assists', 'ownGoals', 'shotsOnTarget', 'kicks'],
  Passing: ['completedPasses', 'passesReceived', 'progressivePasses', 'keyPasses'],
  Defence: ['recoveries', 'possessionLosses'],
};
const number = (value, digits = 0) => Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: digits }) : '—';
const duration = ticks => `${Math.floor(ticks / 3600)}:${String(Math.floor(ticks / 60) % 60).padStart(2, '0')}`;
const percent = (value, total) => `${total ? Math.round(value / total * 100) : 0}%`;
const available = (game, key) => !(['shotsOnTarget', 'keyPasses'].includes(key) && game.shotsAvailable === false)
  && !(key === 'progressivePasses' && !game.territoryAvailable);
function MetricGuide() {
  return <details className="collapse collapse-arrow border border-base-300 bg-base-200/40">
    <summary className="collapse-title py-3 text-sm font-medium">How these stats are counted</summary>
    <dl className="collapse-content grid gap-4 text-xs leading-relaxed sm:grid-cols-2">
      {Object.entries(descriptions).map(([key, text]) => <div key={key}><dt className="font-semibold">{key === 'possessionTicks' ? 'Possession' : V2_MAP_LABELS[key]}</dt><dd className="mt-1 text-base-content/65">{text}</dd></div>)}
    </dl>
  </details>;
}
function TeamMetric({ label, red, blue, description }) {
  return <div className="grid grid-cols-[minmax(3rem,1fr)_minmax(0,2fr)_minmax(3rem,1fr)] items-center gap-3 border-b border-base-300/60 py-3 text-sm">
    <span className="font-mono font-semibold text-error">{number(red)}</span>
    <span className="text-center text-base-content/65" title={description}>{label}</span>
    <span className="text-right font-mono font-semibold text-info">{number(blue)}</span>
  </div>;
}
export function V2Overview({ game }) {
  const { red, blue } = game.teams;
  const possessionTotal = red.possessionTicks + blue.possessionTicks;
  const redShare = possessionTotal ? red.possessionTicks / possessionTotal : 0.5;
  const redGoal = game.stadium.goals.find(goal => goal.team === 'red');
  const blueGoal = game.stadium.goals.find(goal => goal.team === 'blue');
  const pitchAligned = redGoal && blueGoal && redGoal.p0[0] < blueGoal.p0[0]
    && Math.abs((redGoal.p0[1] + redGoal.p1[1]) - (blueGoal.p0[1] + blueGoal.p1[1])) < 0.001;
  const metrics = ['observedGoalsFor', 'assists', 'ownGoals', 'kicks', 'shotsOnTarget', 'completedPasses', 'progressivePasses', 'keyPasses', 'recoveries', 'possessionLosses'];
  return <div className="space-y-6">
    <div className="grid items-start gap-8 xl:grid-cols-2">
      <section aria-label="Team statistics">
        <div className="mb-4 flex justify-between text-xs font-semibold"><span className="text-error">Red team</span><h3 className="text-base-content">Team statistics</h3><span className="text-info">Blue team</span></div>
        <div className="mb-2" aria-label={`Possession: red ${possessionTotal ? percent(red.possessionTicks, possessionTotal) : 'unavailable'}, blue ${possessionTotal ? percent(blue.possessionTicks, possessionTotal) : 'unavailable'}`}>
          <div className="mb-2 flex justify-between text-sm"><span className="font-mono font-semibold text-error">{possessionTotal ? percent(red.possessionTicks, possessionTotal) : '—'}</span><span title={descriptions.possessionTicks} className="text-base-content/65">Possession</span><span className="font-mono font-semibold text-info">{possessionTotal ? percent(blue.possessionTicks, possessionTotal) : '—'}</span></div>
          <div className="flex h-1.5 gap-1 overflow-hidden rounded-full"><div className="rounded-full bg-error/65" style={{ width: `${redShare * 100}%` }} /><div className="flex-1 rounded-full bg-info/65" /></div>
        </div>
        {metrics.map(key => <TeamMetric key={key} label={key === 'observedGoalsFor' ? 'Goals' : V2_MAP_LABELS[key]} description={available(game, key) ? descriptions[key] : 'Unavailable for this pitch.'} red={available(game, key) ? red[key] : null} blue={available(game, key) ? blue[key] : null} />)}
      </section>
      <section aria-label="Ball territory" className="min-w-0 xl:border-l xl:border-base-300 xl:pl-8">
        <h3 className="mb-4 text-sm font-semibold">Ball territory</h3>
        {game.territoryAvailable ? (pitchAligned ? <ThirdsMap game={game} /> : <div><p className="mb-3 text-xs text-base-content/55">Time in each third</p><dl className="grid grid-cols-3 gap-2">{['Red third', 'Middle', 'Blue third'].map((label, index) => <div key={label} className="rounded-field bg-base-200 p-4 text-center"><dt className="text-xs text-base-content/60">{label}</dt><dd className="mt-2 font-mono text-xl">{percent(game.thirds[index], game.activeTicks)}</dd></div>)}</dl></div>) : <p className="py-8 text-sm text-base-content/55">Ball territory is unavailable for this pitch.</p>}
        <p className="mt-3 text-xs text-base-content/55">Ball time in three equal pitch regions.</p>
      </section>
    </div>
    <MetricGuide />
  </div>;
}

export function V2Players({ game, selectedPlayer, onSelect, mapStatistic, onStatistic }) {
  const [sort, setSort] = useState(null);
  const [group, setGroup] = useState('Attack');
  const visibleStatistic = Object.hasOwn(V2_MAP_LABELS, mapStatistic) ? mapStatistic : 'heatmap';
  const player = game.players.find(p => p.id === selectedPlayer) || game.players.find(p => p.team === 'red') || game.players[0];
  const players = [...game.players].sort((a, b) => sort
    ? (a[sort.key] - b[sort.key]) * (sort.direction === 'asc' ? 1 : -1) || a.nick.localeCompare(b.nick)
    : Number(a.team === 'blue') - Number(b.team === 'blue'));
  function show(item, statistic = 'heatmap') { onSelect(item.id); onStatistic(statistic); }
  function cycle(key) { setSort(current => current?.key !== key ? { key, direction: 'desc' } : current.direction === 'desc' ? { key, direction: 'asc' } : null); }
  const columns = [...groups[group].map(key => [key, V2_MAP_LABELS[key]]), ['activeTicks', 'Played']];
  return <div className="@container space-y-6">
    <div className="grid items-start gap-6 @min-[80rem]:grid-cols-2">
      <div className="min-w-0">
        <div role="tablist" aria-label="Player statistic groups" className="tabs tabs-border tabs-sm mb-4 w-fit">
          {Object.keys(groups).map(label => <button key={label} type="button" role="tab" aria-selected={group === label} className={`tab ${group === label ? 'tab-active' : ''}`} onClick={() => { setGroup(label); setSort(null); }}>{label}</button>)}
        </div>
        <div className="overflow-x-auto"><table className="table table-sm">
          <caption className="sr-only">Player statistics. Click a row for its heatmap or a statistic for its event map.</caption>
          <thead><tr><th className="min-w-32">Player</th>{columns.map(([key, label]) => <th key={key} className="text-right" aria-sort={sort?.key === key ? (sort.direction === 'asc' ? 'ascending' : 'descending') : undefined}><button className="btn btn-ghost btn-xs whitespace-nowrap" title={descriptions[key]} onClick={() => cycle(key)}>{label}{sort?.key === key && (sort.direction === 'asc' ? <ArrowUp className="size-3" aria-hidden="true" /> : <ArrowDown className="size-3" aria-hidden="true" />)}</button></th>)}</tr></thead>
          <tbody>{players.map(item => <tr key={item.id} onClick={() => show(item)} className={`cursor-pointer transition-colors ${player?.id === item.id ? 'bg-base-200 hover:bg-base-300/60' : 'hover:bg-base-200/70'}`}>
            <th><button className="flex items-center gap-3 rounded-field py-2 text-left focus-visible:outline-2" aria-pressed={player?.id === item.id}><span className={`size-2 shrink-0 rounded-full ${item.team === 'red' ? 'bg-error' : 'bg-info'}`} />{item.nick}</button></th>
            {columns.map(([key, label]) => <td key={key} className="text-right font-mono">{key === 'activeTicks' ? <span className="px-2">{duration(item.activeTicks)}</span> : !available(game, key) ? <span className="px-2" title="Unavailable for this pitch.">—</span> : <button className="btn btn-ghost btn-xs font-mono" aria-label={`${label} map for ${item.nick}`} aria-pressed={player?.id === item.id && visibleStatistic === key} onClick={event => { event.stopPropagation(); show(item, key); }}>{item[key]}</button>}</td>)}
          </tr>)}</tbody>
        </table></div>
        <p className="mt-4 text-xs leading-relaxed text-base-content/55">Click a player to see their heatmap, or a statistic to see where it happened.</p>
      </div>
      <div className="min-w-0">
        <PlayerMaps game={game} player={player} statistic={available(game, visibleStatistic) ? visibleStatistic : 'heatmap'} onStatistic={onStatistic} labels={Object.fromEntries(Object.entries(V2_MAP_LABELS).filter(([key]) => available(game, key)))} />
        {available(game, visibleStatistic) && descriptions[visibleStatistic] && <p className="mt-3 text-xs leading-relaxed text-base-content/65">{descriptions[visibleStatistic]}</p>}
      </div>
    </div>
    <MetricGuide />
  </div>;
}
