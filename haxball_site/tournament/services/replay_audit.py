"""Match-level relevance policy shared by ingestion and read-only audits."""

from collections import Counter

TICKS_PER_SECOND = 60
HALF_SECONDS = 480
FULL_PART_SECONDS = 450  # Recognition tolerance, never an official playing-time cutoff.


def exclusion_description(decision):
    """Describe strong exclusion evidence; review-only signals never become exclusions."""
    reasons = []
    roster = decision['roster']
    if 'fewer_than_required_players' in decision['reasons']:
        reasons.append(
            'Недостаточный состав за всю игру '
            f'(красные: {roster["sides"]["red"]["total"]}, синие: {roster["sides"]["blue"]["total"]}).'
        )
    if 'major_protocol_mismatch' in decision['reasons']:
        reasons.append('Состав игроков существенно отличается от участников протокола матча.')
    if 'short_extra_beside_two_full_halves' in decision['reasons']:
        seconds = round(decision['seconds'])
        reasons.append(
            f'Короткая дополнительная игра ({seconds // 60}:{seconds % 60:02}) при наличии двух полных таймов.'
        )
    return ' '.join(reasons)


def normalize_nick(nick):
    return nick.strip().casefold()


def roster_evidence(raw, protocol, aliases, required_players=4):
    """Count identities across the whole game, including late joiners and substitutes.

    Unique historical nicknames can identify people; ambiguous/unrecognized nicknames
    are unknown, not proof that someone played outside the official protocol.
    """
    sides = {}
    protocol_complete = all(len(protocol[side]) >= required_players for side in ('home', 'away'))
    for side in ('red', 'blue'):
        people = {}
        for player in raw['players']:
            if player['team'] != side or player['playedTicks'] <= 0:
                continue
            nick = normalize_nick(player['nick'])
            ids = aliases.get(nick, set())
            identity = next(iter(ids)) if len(ids) == 1 else None
            key = ('player', identity) if identity is not None else ('nick', nick)
            people[key] = (player['nick'], identity)
        counts = Counter()
        names = {'home': [], 'away': [], 'outside': [], 'unknown': []}
        for nick, identity in people.values():
            if identity is None:
                group = 'unknown'
            elif identity in protocol['home']:
                group = 'home'
            elif identity in protocol['away']:
                group = 'away'
            else:
                group = 'outside'
            counts[group] += 1
            names[group].append(nick)
        sides[side] = {'total': len(people), **{k: counts[k] for k in names}, 'names': names}
    normal = sides['red']['home'] + sides['blue']['away']
    swapped = sides['red']['away'] + sides['blue']['home']
    votes_for_normal = bool(normal)
    votes_for_swapped = bool(swapped)
    mapping = (
        'conflict'
        if votes_for_normal and votes_for_swapped
        else ('roster' if votes_for_normal or votes_for_swapped else 'default')
    )
    total = sum(s['total'] for s in sides.values())
    outside = sum(s['outside'] for s in sides.values())
    matched = normal + swapped
    # Require identifiable outsiders, a complete protocol and a majority mismatch.
    different_opponent = any(
        s['outside'] >= required_players and s['outside'] >= s['total'] * 0.75 for s in sides.values()
    )
    mismatch = (
        protocol_complete
        and outside >= required_players
        and ((outside > total / 2 and matched < total / 2) or different_opponent)
    )
    return {
        'sides': sides,
        'protocol_complete': protocol_complete,
        'incomplete': any(s['total'] < required_players for s in sides.values()),
        'major_mismatch': mismatch,
        'matched': matched,
        'unknown': sum(s['unknown'] for s in sides.values()),
        'mapping': mapping,
        'red_is_home': mapping != 'roster' or normal > swapped,
    }


def evaluate_match(games, protocol, aliases, *, playoff=False, duration_seconds=960, required_players=4):
    """Return explainable suggestions; never mutate inputs or saved inclusion flags.

    `games` are in source-list/game order, not an invented wall-clock chronology.
    Each has `raw`, stable DB/source references and optional editorial metadata.
    """
    results = []
    issues = []
    if not all(len(protocol[s]) >= required_players for s in ('home', 'away')):
        issues.append('incomplete_protocol')
    for game in games:
        raw = game['raw']
        roster = roster_evidence(raw, protocol, aliases, required_players)
        seconds = raw['gameTicks'] / TICKS_PER_SECOND
        reasons = []
        if roster['incomplete']:
            reasons.append('fewer_than_required_players')
        if roster['major_mismatch']:
            reasons.append('major_protocol_mismatch')
        result = {
            **{k: v for k, v in game.items() if k != 'raw'},
            'seconds': round(seconds, 2),
            'score': [raw['scoreRed'], raw['scoreBlue']],
            'roster': roster,
            'recommendation': 'exclude' if reasons else 'retain',
            'role': 'irrelevant_candidate' if reasons else 'unclassified',
            'reasons': reasons,
            'after_eight_minute_goals': sum(g.get('gameTick', 0) > HALF_SECONDS * 60 for g in raw['goals']),
        }
        if roster['mapping'] == 'conflict':
            result['reasons'].append('conflicting_side_evidence')
        if not roster['incomplete'] and roster['unknown'] > (sum(s['total'] for s in roster['sides'].values()) / 2):
            result['reasons'].append('mostly_unresolved_nicknames')
        results.append(result)

    candidates = [
        i
        for i, r in enumerate(results)
        if r['recommendation'] != 'exclude' and games[i].get('included_override') is not False
    ]
    anchors = [
        i
        for i in candidates
        if results[i]['seconds'] >= FULL_PART_SECONDS and games[i].get('included_override') is not False
    ]
    for n, index in enumerate(anchors):
        results[index]['role'] = (
            'regulation_candidate' if n < 2 else 'overtime_candidate' if playoff else 'extra_full_game'
        )
        if results[index]['seconds'] < HALF_SECONDS - 2:
            results[index]['reasons'].append('short_of_eight_minutes')
        if n >= 2:
            results[index]['recommendation'] = 'review'
            results[index]['reasons'].append('overtime_rules_need_review' if playoff else 'extra_full_game')

    # Adjacent shorter games may make up an interrupted half (7+1, 3+5, etc.).
    # Never exclude these just because one fragment is short or scoreless.
    continuation_indices = set()
    if len(anchors) < 2:
        for start in range(len(candidates)):
            group = []
            for index in candidates[start : start + 4]:
                if results[index]['seconds'] >= FULL_PART_SECONDS:
                    break
                group.append(index)
                total = sum(results[i]['seconds'] for i in group)
                if len(group) >= 2 and HALF_SECONDS - 15 <= total <= HALF_SECONDS + 15:
                    continuation_indices.update(group)
                    for i in group:
                        results[i]['role'] = 'possible_continuation'
                        results[i]['recommendation'] = 'review'
                        results[i]['reasons'].append('possible_split_half')
                if total > HALF_SECONDS + 15:
                    break

    for index in candidates:
        r = results[index]
        if index in anchors or index in continuation_indices:
            continue
        # Preserve short golden-goal candidates after regulation; duration/score
        # cannot establish the competition's overtime rule on their own.
        if playoff and len(anchors) >= 2 and index > anchors[1]:
            r['role'] = 'overtime_candidate'
            r['recommendation'] = 'review'
            r['reasons'].append('possible_golden_goal_or_restart')
        elif len(anchors) >= 2 and r['seconds'] < HALF_SECONDS / 2:
            r['role'] = 'restart_candidate'
            r['recommendation'] = 'exclude'
            r['reasons'].append('short_extra_beside_two_full_halves')
        else:
            r['recommendation'] = 'review'
            r['reasons'].append('short_game_without_clear_role')

    retained = [r for r in results if r['recommendation'] != 'exclude' and r.get('included_override') is not False]
    if len(retained) < 2:
        issues.append('fewer_than_two_plausible_games')
    if len(anchors) < 2:
        issues.append('regulation_coverage_uncertain')
    if len(anchors) > 2 and not playoff:
        issues.append('more_than_two_full_regulation_candidates')
    coverage = sum(min(r['seconds'], HALF_SECONDS) for r in retained)
    if coverage < duration_seconds - 30:
        issues.append('recorded_time_short_of_match_duration')
    if any(r['recommendation'] == 'exclude' and r['seconds'] >= FULL_PART_SECONDS for r in results):
        issues.append('full_length_game_with_strong_roster_problem')

    # A score discrepancy only requests review; fair-play goals are legitimate
    # exceptions. Do not solve subset selection by forcing official-score equality.
    score = [0, 0]
    for game, result in zip(games, results, strict=True):
        if result['recommendation'] == 'exclude' or game.get('included_override') is False:
            continue
        red_is_home = game.get('red_is_home_override')
        if red_is_home is None:
            red_is_home = result['roster']['red_is_home']
        for goal in game['raw']['goals']:
            if goal.get('gameTick') is None or goal['gameTick'] > HALF_SECONDS * 60:
                continue
            home_goal = (goal['team'] == 'red') == red_is_home
            score[0 if home_goal else 1] += 1
    return {'games': results, 'issues': issues, 'window_score': score, 'coverage_seconds': round(coverage, 2)}
