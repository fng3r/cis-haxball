import { ArrowLeft, RotateCcw } from 'lucide-react';

export default function MatchContext({ context, loading, error, onRetry, mapping, onMapping, game }) {
  if (error) return <div role="alert" className="alert"><span>{error}</span><button className="btn btn-sm" onClick={onRetry}><RotateCcw className="size-4" aria-hidden="true" />Retry match import</button></div>;
  if (!context) return loading && <p role="status">Loading match recordings…</p>;
  const match = context.match;
  return <section className="rounded-box border border-base-300 bg-base-100 p-4 space-y-3" aria-label="Match context">
    <a className="btn btn-sm" href={match.url}><ArrowLeft className="size-4" aria-hidden="true" />Back to match #{match.id}</a>
    <p className="text-sm text-base-content/65">{[match.season, match.league, match.stage, match.group, match.tour].filter(Boolean).map(item => item.name).join(' · ')}</p>
    <p className="text-sm">{context.teams.home.name} — {context.teams.away.name}{match.isPlayed && ` · Official score ${match.officialScore.join(':')}`}</p>
    <p className="text-xs text-base-content/55">Replay statistics cover the recorded play. {loading ? 'Downloading recordings…' : ''}</p>
    {game && <label className="flex flex-wrap items-center gap-3 text-sm">{mapping === null ? 'Team mapping unresolved · Red / Blue' : 'Replay sides'}
      {context.canMap ? <select className="select select-sm w-full sm:w-auto" aria-label="Red side team" value={mapping === null ? '' : String(mapping)} onChange={event => onMapping(event.target.value === '' ? null : event.target.value === 'true')}>
        <option value="">Unresolved — Red / Blue</option><option value="true">Red: {context.teams.home.name}</option><option value="false">Red: {context.teams.away.name}</option>
      </select> : mapping === null && <span className="text-xs text-base-content/55">A match statistics editor can resolve the sides.</span>}
    </label>}
  </section>;
}

export function TeamIdentity({ team, fallback }) {
  return <span className="inline-flex items-center gap-2">{team?.logo && <img src={team.logo} alt="" className="size-7 object-contain" />}{team?.name || fallback}</span>;
}
