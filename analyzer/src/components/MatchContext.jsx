import { ArrowLeft, RotateCcw } from 'lucide-react';

export default function MatchContext({ context, loading, error, onRetry, part }) {
  if (error) return <div role="alert" className="alert"><span>{error}</span><button className="btn btn-sm" onClick={onRetry}><RotateCcw className="size-4" aria-hidden="true" />Retry match import</button></div>;
  if (!context) return loading && <p role="status">Loading match recordings…</p>;
  const match = context.match;
  return <section className="rounded-box border border-base-300 bg-base-100 p-4 space-y-3" aria-label="Match context">
    <a className="btn btn-sm" href={match.url}><ArrowLeft className="size-4" aria-hidden="true" />Back to match #{match.id}</a>
    <p className="text-sm text-base-content/65">{[match.season, match.league, match.stage, match.group, match.tour].filter(Boolean).map(item => item.name).join(' · ')}</p>
    <p className="text-sm">{context.teams.home.name} — {context.teams.away.name}{match.isPlayed && ` · Official score ${match.officialScore.join(':')}`}</p>
    <p className="text-xs text-base-content/55">Replay statistics cover the recorded play. {loading ? 'Downloading recordings…' : ''}</p>
    {part && <p className="text-sm">{part.label}{!part.included && ' · Excluded from match statistics'}</p>}

  </section>;
}

export function TeamIdentity({ team, fallback }) {
  return <span className="inline-flex items-center gap-2">{team?.logo && <img src={team.logo} alt="" className="size-7 object-contain" />}{team?.name || fallback}</span>;
}
