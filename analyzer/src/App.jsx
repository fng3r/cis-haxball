import { useEffect, useRef, useState } from 'react';
import NativePlayer from './components/NativePlayer.jsx';
import ReplayLinkForm from './components/ReplayLinkForm.jsx';
import PlayerMaps from './components/PlayerMaps.jsx';
import ThirdsMap from './components/ThirdsMap.jsx';
import { serializeStats } from './export-stats.js';
import { useReplayLibrary } from './useReplayLibrary.js';

export function time(ticks = 0) {
  const seconds = Math.max(0, Math.floor(ticks / 60));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

function Mark() {
  return <svg viewBox="0 0 40 40" className="size-10" fill="none" aria-hidden="true">
    <rect x="2" y="5" width="36" height="30" rx="8" stroke="currentColor" strokeWidth="1.5" />
    <path d="M20 5v30M2 14h5v12H2m36-12h-5v12h5" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="20" cy="20" r="6" stroke="currentColor" strokeWidth="1.5" />
  </svg>;
}

function Comparison({ label, values, percentage = false }) {
  const total = values[0] + values[1];
  const fraction = total ? values[0] / total : 0.5;
  const display = value => percentage ? `${total ? Math.round(value / total * 100) : 0}%` : value;
  return <div className="space-y-2">
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="w-12 font-mono font-semibold text-error">{display(values[0])}</span>
      <span className="text-base-content/65">{label}</span>
      <span className="w-12 text-right font-mono font-semibold text-info">{display(values[1])}</span>
    </div>
    <div className="flex h-1.5 gap-1 overflow-hidden rounded-full" aria-label={`${label}: red ${display(values[0])}, blue ${display(values[1])}`}>
      <div className="rounded-full bg-error/65" style={{ width: `${fraction * 100}%` }} />
      <div className="flex-1 rounded-full bg-info/65" />
    </div>
  </div>;
}

function GoalList({ game, onSeek }) {
  if (!game.goals.length) return <p className="py-8 text-sm text-base-content/55">No goals in this game.</p>;
  return <div className="mx-auto max-w-3xl">
    <div className="mb-3 grid grid-cols-[minmax(0,1fr)_5rem_minmax(0,1fr)] items-center gap-2 text-xs font-semibold">
      <span className="pr-3 text-right text-error">Red team</span>
      <span className="text-center text-base-content/45">Score</span>
      <span className="pl-3 text-info">Blue team</span>
    </div>
    <ol className="timeline timeline-vertical" aria-label="Goal timeline">
      {game.goals.map((goal, i) => <li key={i} className="h-16 w-full">
        {i > 0 && <hr />}
        <button className={`${goal.team === 'red' ? 'timeline-start text-right hover:bg-error/10' : 'timeline-end text-left hover:bg-info/10'} min-w-0 max-w-full rounded-field px-3 py-2 focus-visible:outline-2`} onClick={() => onSeek(goal.tick)} aria-label={`Watch ${goal.scorer || 'unattributed'}${goal.ownGoal ? ' own' : ''} goal at ${time(goal.gameTick)}, score ${goal.scoreRed}–${goal.scoreBlue}`}>
          <span title={`${goal.scorer || 'Unattributed goal'}${goal.ownGoal ? ' (own goal)' : ''}`} className={`block truncate text-sm font-semibold ${goal.team === 'red' ? 'text-error' : 'text-info'}`}>{goal.scorer || 'Unattributed goal'}{goal.ownGoal ? ' (own goal)' : ''}</span>
          {goal.assist && <span title={`Assist · ${goal.assist}`} className="mt-1 block truncate text-xs text-base-content/55">Assist · {goal.assist}</span>}
        </button>
        <div className="timeline-middle flex w-20 flex-col items-center gap-1 rounded-field border border-base-300 bg-base-100 py-2">
          <span className="font-mono text-sm font-semibold">{goal.scoreRed}:{goal.scoreBlue}</span>
          <time className="font-mono text-[10px] text-base-content/50">{time(goal.gameTick)}</time>
        </div>
        {i < game.goals.length - 1 && <hr />}
      </li>)}
    </ol>
  </div>;
}

function PlayerTable({ game, selectedPlayer, onSelect }) {
  const [sort, setSort] = useState(null);
  const [mapStatistic, setMapStatistic] = useState('heatmap');
  const mappedPlayer = game.players.find(player => player.id === selectedPlayer)
    || game.players.find(player => player.team === 'red') || game.players[0];
  function showMap(player, statistic) { onSelect(player.id); setMapStatistic(statistic); }
  const teamOrder = { red: 0, blue: 1 };
  const players = [...game.players].sort((a, b) => !sort
    ? teamOrder[a.team] - teamOrder[b.team]
    : (a[sort.key] - b[sort.key]) * (sort.direction === 'asc' ? 1 : -1) || a.nick.localeCompare(b.nick));
  function cycleSort(key) {
    setSort(current => current?.key !== key ? { key, direction: 'desc' }
      : current.direction === 'desc' ? { key, direction: 'asc' } : null);
  }
  const columns = [['goals', 'Goals'], ['assists', 'Assists'], ['kicks', 'Kicks'], ['passes', 'Passes'], ['shots', 'On target'], ['playedTicks', 'Played']];
  return <div className="@container"><div className="grid items-start gap-6 @min-[80rem]:grid-cols-2"><div className="min-w-0"><div className="overflow-x-auto">
    <table className="table table-sm">
      <caption className="sr-only">Player statistics. Select a player for their heatmap, or a statistic for its event map.</caption>
      <thead><tr><th className="min-w-40">Player</th>{columns.map(([key, label]) => <th key={key} className="text-right" aria-sort={sort?.key === key ? (sort.direction === 'asc' ? 'ascending' : 'descending') : undefined}>
        <button className="btn btn-ghost btn-xs whitespace-nowrap" aria-pressed={sort?.key === key} title={sort?.key !== key ? 'Sort descending' : sort.direction === 'desc' ? 'Sort ascending' : 'Reset to team order'} onClick={() => cycleSort(key)}>{label}{sort?.key === key ? (sort.direction === 'asc' ? ' ↑' : ' ↓') : ''}</button>
      </th>)}</tr></thead>
      <tbody>{players.map(player => <tr key={player.id} className={selectedPlayer === player.id ? 'bg-base-200' : ''}>
        <th><button className="flex items-center gap-3 rounded-field py-2 text-left focus-visible:outline-2" aria-pressed={selectedPlayer === player.id} onMouseEnter={() => showMap(player, 'heatmap')} onFocus={() => showMap(player, 'heatmap')} onClick={() => showMap(player, 'heatmap')}>
          <span className={`size-2 shrink-0 rounded-full ${player.team === 'red' ? 'bg-error' : 'bg-info'}`} />
          {player.nick}</button></th>
        {columns.map(([key, label]) => <td key={key} className="text-right font-mono"><button className="btn btn-ghost btn-xs font-mono" aria-label={`${label} map for ${player.nick}`} aria-pressed={selectedPlayer === player.id && mapStatistic === (key === 'playedTicks' ? 'heatmap' : key)} onClick={() => showMap(player, key === 'playedTicks' ? 'heatmap' : key)}>{key === 'playedTicks' ? time(player[key]) : player[key]}</button></td>)}
      </tr>)}</tbody>
    </table>
    </div>
    <p className="mt-4 px-2 text-xs text-base-content/50">Hover or select a player for their heatmap. Select a statistic to map its events. Passes count completed passes; shots count shots on goal.</p>
    </div>
    <PlayerMaps game={game} player={mappedPlayer} statistic={mapStatistic} onStatistic={setMapStatistic} />
  </div></div>;
}

export default function App() {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('replay-theme') === 'replay' ? 'replay' : 'replay-dark'; }
    catch { return 'replay-dark'; }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = theme === 'replay' ? '#f3f4f9' : '#171b29';
    try { localStorage.setItem('replay-theme', theme); } catch {}
  }, [theme]);
  const { recordings, recording, active, addFiles, cancel, clear, remove, retry, select } = useReplayLibrary();
  const replay = recording?.result;
  const filename = recording?.file.name || '';
  const busy = Boolean(active);
  const progress = active?.progress || 0;
  const [gameIndex, setGameIndex] = useState(0);
  const nativePlayer = useRef(null);
  const playerCard = useRef(null), statsCard = useRef(null);
  const [selectedPlayer, setSelectedPlayer] = useState(null);
  const [tab, setTab] = useState('overview');
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState(false);
  const input = useRef(null);
  const game = replay?.games[gameIndex];

  useEffect(() => {
    setGameIndex(0); setSelectedPlayer(null); setTab('overview');
  }, [recording?.id]);

  function open(files) {
    setError(addFiles(files).join(' '));
  }

  function selectGame(index) {
    setGameIndex(index); setSelectedPlayer(null);
    nativePlayer.current?.seek(replay.games[index].startTick);
  }
  function scrollToCard(card) {
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    card.current?.scrollIntoView({ behavior: reducedMotion ? 'instant' : 'smooth', block: 'start' });
  }
  function showStats() {
    setTab('overview');
    scrollToCard(statsCard);
  }
  function seekGoal(tick) {
    nativePlayer.current?.seekGoal(tick);
    scrollToCard(playerCard);
  }
  function onPlayerGoal(tick) {
    const index = replay?.games.findIndex(game => game.goals.some(goal => goal.tick === tick));
    onPlayerGame(index);
  }
  function onPlayerGame(index) {
    if (Number.isInteger(index) && index >= 0 && index < (replay?.games.length || 0) && index !== gameIndex) {
      setGameIndex(index);
      setSelectedPlayer(null);
    }
  }
  function exportStats() {
    const json = serializeStats(replay);
    const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `${filename.replace(/\.hbr2$/i, '')}-stats.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <div className="min-h-screen">
    <header className="border-b border-base-300 bg-base-100">
      <div className="flex items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3"><Mark /><div><h1 className="text-xl font-extrabold tracking-tight">REPLAY<span className="ml-1 font-normal">LAB</span></h1><p className="text-[10px] font-semibold tracking-[0.18em] text-base-content/50">HAXBALL MATCH ANALYSIS</p></div></div>
        <div className="flex items-center gap-2 sm:gap-5"><button className="btn btn-sm btn-square" aria-label={theme === 'replay-dark' ? 'Switch to light mode' : 'Switch to dark mode'} title={theme === 'replay-dark' ? 'Switch to light mode' : 'Switch to dark mode'} onClick={() => setTheme(theme === 'replay-dark' ? 'replay' : 'replay-dark')}><span aria-hidden="true">{theme === 'replay-dark' ? '☀' : '☾'}</span></button></div>
      </div>
    </header>
    <input ref={input} type="file" accept=".hbr2" multiple aria-label="Open HaxBall replay" className="sr-only" onChange={event => { open(event.target.files); event.target.value = ''; }} />
    <main className="grid gap-6 p-4 lg:grid-cols-[240px_minmax(0,1fr)]">
      <aside className="space-y-6 lg:sticky lg:top-4 lg:max-h-[calc(100dvh-2rem)] lg:self-start lg:overflow-y-auto">
        <div onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); open(event.dataTransfer.files); }} className={`rounded-box border border-dashed p-5 ${dragging ? 'border-primary bg-primary/5' : 'border-base-content/25 bg-base-100/50'}`}>
          <h3 className="font-semibold">Bring your replays.</h3><p className="mb-5 mt-2 text-xs leading-relaxed text-base-content/60">Drop .hbr2 files here, or choose recordings from your device.</p>
          <button className="btn btn-primary btn-sm w-full" onClick={() => input.current.click()}>Choose recordings</button>
          <ReplayLinkForm onFiles={open} />
          <p className="mt-3 text-center text-[11px] text-base-content/45">32 MB per file · Analyzed on your device</p>
        </div>
        {recordings.length > 0 && <section aria-label="Recordings">
          <div className="mb-3 flex items-center justify-between gap-2 text-xs font-semibold uppercase tracking-wider text-base-content/50"><span>Recordings · {recordings.length}</span><button className="btn btn-ghost btn-xs normal-case tracking-normal" aria-label="Clear all recordings" onClick={() => { setError(''); clear(); }}>Clear all</button></div>
          <div className="space-y-2">{recordings.map(item => <div key={item.id} className={`rounded-box border p-3 ${recording?.id === item.id ? 'border-base-content/30 bg-base-100' : 'border-base-300'}`}>
            <div className="flex items-start gap-2">
              <button className="min-w-0 flex-1 rounded-field text-left focus-visible:outline-2" aria-label={`Open recording ${item.file.name}`} aria-pressed={recording?.id === item.id} onClick={() => { setError(''); select(item.id); }}>
                <span className="block truncate text-xs font-semibold" title={item.file.name}>{item.file.name}</span>
                <span className={`mt-1 block text-[11px] ${item.status === 'error' ? 'text-error' : 'text-base-content/55'}`}>{item.status === 'ready' ? `${item.result.games.length} games` : item.status === 'analyzing' ? `Analyzing… ${item.progress}%` : item.status === 'error' ? 'Analysis failed' : item.status === 'cancelled' ? 'Cancelled' : 'Queued'}</span>
              </button>
              <button className="btn btn-ghost btn-xs btn-square shrink-0" aria-label={`Remove recording ${item.file.name}`} onClick={() => { setError(''); remove(item.id); }}>×</button>
            </div>
            {['error', 'cancelled'].includes(item.status) && <button className="btn btn-ghost btn-xs mt-2" aria-label={`Retry analysis of ${item.file.name}`} onClick={() => retry(item.id)}>Retry analysis</button>}
          </div>)}</div>
        </section>}
        {replay && <section aria-label="Games in recording">
          <div className="mb-3 flex justify-between text-xs font-semibold uppercase tracking-wider text-base-content/50"><span>Games</span><span>{replay.games.length}</span></div>
          <div className="space-y-2">{replay.games.map((item, index) => <button key={item.id} aria-pressed={gameIndex === index} onClick={() => selectGame(index)} className={`w-full rounded-box border p-4 text-left ${gameIndex === index ? 'border-base-content/30 bg-base-100 shadow-sm' : 'border-transparent hover:bg-base-100/60'}`}>
            <div className="flex justify-between text-sm font-semibold"><span>Game {index + 1}</span><span className="font-mono"><span className="text-error">{item.scoreRed}</span><span className="px-2 text-base-content/30">:</span><span className="text-info">{item.scoreBlue}</span></span></div>
            <p className="mt-2 truncate text-xs text-base-content/55">{time(item.gameTicks)} · {item.stadium.name}</p>
          </button>)}</div>
        </section>}
        <div className="border-t border-base-300 pt-5 text-xs leading-relaxed text-base-content/50"><p className="font-semibold text-base-content/75">Keep the game in perspective.</p><p className="mt-2">Explore possession, passes, shots and the moments that changed the score.</p></div>
      </aside>
      <div className="min-w-0 space-y-6">
        {error && <div role="alert" className="alert alert-error"><span>{error}</span><button className="btn btn-sm" onClick={() => setError('')}>Dismiss</button></div>}
        {recording?.status === 'error' && <div role="alert" className="alert alert-error"><span>{recording.file.name}: {recording.error}</span></div>}
        {busy && <section className="rounded-box border border-base-300 bg-base-100 p-5" aria-live="polite" aria-busy="true">
          <div className="mb-3 flex items-center justify-between gap-4"><div><h2 className="font-semibold">Analyzing recording… {progress}%</h2><p className="mt-1 truncate text-xs text-base-content/60">{active.file.name} · {recordings.filter(item => item.status === 'queued').length} queued</p></div><button className="btn btn-sm" title="Cancel current and queued analyses" onClick={cancel}>Cancel</button></div>
          <progress className="progress w-full" value={progress} max="100" />
        </section>}
        <section ref={playerCard} className="scroll-mt-4 overflow-hidden rounded-box border border-base-300 bg-base-100">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-base-300 px-5 py-3 sm:px-7">
            <div><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-base-content/45">Replay workspace</p><h2 className="mt-1 max-w-64 truncate text-sm font-semibold sm:max-w-96">{game ? filename : 'Every match has a story.'}</h2></div>
            {replay ? <button className="btn btn-sm" onClick={exportStats}>Export statistics ↓</button> : <span className="text-xs text-base-content/45">.hbr2 recordings</span>}
          </div>
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 px-5 py-3 sm:px-7">
            <div className="flex items-center gap-3 text-sm font-semibold"><span className="h-8 w-1 rounded-full bg-error" /><div>Red team<p className="mt-1 text-[11px] font-normal text-base-content/45">{game ? `${game.players.filter(p => p.team === 'red').length} players` : 'Home side'}</p></div></div>
            <div className="text-center"><div className="flex items-center justify-center gap-4 font-mono text-3xl font-medium tracking-tight sm:text-4xl"><span>{game ? game.scoreRed : '—'}</span><span className="text-2xl text-base-content/25">:</span><span>{game ? game.scoreBlue : '—'}</span></div><p className="mt-2 font-mono text-[11px] text-base-content/50">{game ? `GAME ${gameIndex + 1} · ${time(game.gameTicks)}` : 'READY WHEN YOU ARE'}</p></div>
            <div className="flex items-center justify-end gap-3 text-right text-sm font-semibold"><div>Blue team<p className="mt-1 text-[11px] font-normal text-base-content/45">{game ? `${game.players.filter(p => p.team === 'blue').length} players` : 'Away side'}</p></div><span className="h-8 w-1 rounded-full bg-info" /></div>
          </div>
          <div className="px-3 pb-3">
            {recording ? <NativePlayer key={recording.id} ref={nativePlayer} file={recording.file} games={replay?.games} onGoal={onPlayerGoal} onGame={onPlayerGame} onError={setError} onStats={showStats} onClose={() => { setError(''); remove(recording.id); }} />
              : <div className="flex min-h-72 flex-col items-center justify-center rounded-box bg-neutral p-8 text-center text-neutral-content"><p className="text-sm">Open a recording to watch the replay.</p><p className="mt-3 text-xs opacity-60">The original HaxBall player handles playback.</p></div>}
          </div>
        </section>
        {game ? <section ref={statsCard} className="scroll-mt-4 rounded-box border border-base-300 bg-base-100 p-5 sm:p-7">
          <h2 className="mb-4 text-lg font-semibold">Game {gameIndex + 1}</h2>
          <div role="tablist" aria-label="Match information" className="tabs tabs-border mb-6">{['overview', 'players', 'goals'].map(name => <button key={name} role="tab" id={`tab-${name}`} aria-controls="match-panel" aria-selected={tab === name} className={`tab capitalize ${tab === name ? 'tab-active' : ''}`} onClick={() => setTab(name)}>{name}{name === 'goals' ? ` · ${game.goals.length}` : ''}</button>)}</div>
          <div role="tabpanel" id="match-panel" aria-labelledby={`tab-${tab}`}>
            {tab === 'overview' && <div className="grid gap-8 xl:grid-cols-[1fr_1fr]">
              <div className="space-y-6"><h3 className="text-sm font-semibold">The balance of play</h3><Comparison label="Possession" values={game.possession} percentage /><Comparison label="Kicks" values={game.kicks} /><Comparison label="Completed passes" values={game.passes} /><Comparison label="Shots on goal" values={game.shots} /></div>
              <div className="xl:border-l xl:border-base-300 xl:pl-8"><h3 className="mb-5 text-sm font-semibold">Ball territory</h3><ThirdsMap game={game} /><p className="mt-4 text-xs leading-relaxed text-base-content/55">Where the ball spent its time during active play. Team colors follow the recording.</p><p className="mt-5 text-xs text-base-content/50">{game.spaceMode ? 'SpaceBounce rules detected.' : 'Standard kicking rules.'}</p></div>
            </div>}
            {tab === 'players' && <PlayerTable game={game} selectedPlayer={selectedPlayer} onSelect={setSelectedPlayer} />}
            {tab === 'goals' && <><p className="mb-3 text-xs text-base-content/55">Choose a goal to jump to the build-up.</p><GoalList game={game} onSeek={seekGoal} /></>}
          </div>
        </section> : !busy && <div className="grid gap-5 sm:grid-cols-3">{[['Watch it back', 'Scrub the timeline and revisit every goal.'], ['Read the game', 'Compare possession, passing and shots.'], ['Find the detail', 'Inspect individual player contributions.']].map(([title, text]) => <div key={title} className="border-t border-base-content/20 pt-4"><h3 className="text-sm font-semibold">{title}</h3><p className="mt-2 text-xs leading-relaxed text-base-content/55">{text}</p></div>)}</div>}
      </div>
    </main>
  </div>;
}
