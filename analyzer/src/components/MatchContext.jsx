import { RotateCcw } from 'lucide-react';

export default function MatchContext({ context, loading, error, onRetry }) {
  if (error) return <div role="alert" className="flex items-center gap-2 text-xs"><span>{error}</span><button className="btn btn-sm btn-square" aria-label="Retry match import" title="Retry match import" onClick={onRetry}><RotateCcw className="size-4" aria-hidden="true" /></button></div>;
  if (!context) return loading && <p role="status" className="text-xs text-base-content/60">Loading match…</p>;
  const match = context.match;
  const tourLabel = match.tour && `${match.tour.name}${match.series ? ` (${match.series.matchNumber} матч)` : ''}`;
  return <div className="min-w-0 space-y-1.5" aria-label="Match context">
    <p className="text-xs text-base-content/60">{[match.season?.name, (match.stage || match.league)?.name, tourLabel].filter(Boolean).join(' · ')}</p>
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-semibold">
      <TeamIdentity team={context.teams.home} logoClassName="size-5" />
      <span className="shrink-0 font-mono">{match.isPlayed ? match.officialScore.join(':') : '—'}</span>
      <TeamIdentity team={context.teams.away} logoAfter logoClassName="size-5" />
    </div>
  </div>;
}

export function TeamIdentity({ team, fallback, logoAfter = false, className = '', logoClassName = 'size-7' }) {
  const logo = team?.logo && <img src={team.logo} alt="" className={`${logoClassName} shrink-0 object-contain`} />;
  const name = team?.shortName && team.shortName !== team.name
    ? <span className="min-w-0 break-words"><span className="sm:hidden">{team.shortName}</span><span className="hidden sm:inline">{team.name}</span></span>
    : <span className="min-w-0 break-words">{team?.name || fallback}</span>;
  return <span className={`inline-flex min-w-0 items-center gap-2 ${className}`}>{!logoAfter && logo}{name}{logoAfter && logo}</span>;
}
