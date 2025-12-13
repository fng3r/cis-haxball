from .models import SquadPlayer, SquadSubmission

POINTS_CONFIG = {
    'goals': {
        SquadPlayer.Position.ST: 3,
        SquadPlayer.Position.DM: 4,
        SquadPlayer.Position.GK: 6,
    },
    'assists': {
        SquadPlayer.Position.ST: 2,
        SquadPlayer.Position.DM: 3,
        SquadPlayer.Position.GK: 4,
    },
    'clean_sheet': {
        SquadPlayer.Position.ST: 3,
        SquadPlayer.Position.DM: 10,
        SquadPlayer.Position.GK: 20,
    },
    'conceded_goals': {
        (1, 2): {
            SquadPlayer.Position.ST: 0,
            SquadPlayer.Position.DM: -1,
            SquadPlayer.Position.GK: -1,
        },
        (3, 5): {
            SquadPlayer.Position.ST: -1,
            SquadPlayer.Position.DM: -2,
            SquadPlayer.Position.GK: -2,
        },
        (6, 10): {
            SquadPlayer.Position.ST: -2,
            SquadPlayer.Position.DM: -3,
            SquadPlayer.Position.GK: -4,
        },
        (11, 15): {
            SquadPlayer.Position.ST: -3,
            SquadPlayer.Position.DM: -5,
            SquadPlayer.Position.GK: -6,
        },
        (16, float('inf')): {
            SquadPlayer.Position.ST: -5,
            SquadPlayer.Position.DM: -8,
            SquadPlayer.Position.GK: -10,
        },
    },
}


def calculate_match_points(player, match, position, match_goals, match_cs, match_player_teams):
    """Calculate fantasy points for a player in a specific match with detailed breakdown"""
    goals_count = sum(1 for goal in match_goals if goal.author_id == player.id)
    assists_count = sum(1 for goal in match_goals if goal.assistent_id == player.id)

    player_team = _get_player_team_for_match(player, match, match_player_teams)
    cs_count = _count_clean_sheets(player, match, player_team, match_cs)

    goals_points = goals_count * POINTS_CONFIG['goals'].get(position, POINTS_CONFIG['goals']['ST'])
    assists_points = assists_count * POINTS_CONFIG['assists'].get(position, POINTS_CONFIG['assists']['ST'])
    cs_points = cs_count * POINTS_CONFIG['clean_sheet'].get(position, POINTS_CONFIG['clean_sheet']['ST'])

    seconds_played = _get_player_playtime(player, match)
    if seconds_played >= 12 * 60:
        playtime_points = 3
    elif seconds_played >= 4 * 60:
        playtime_points = 2
    elif seconds_played > 0:
        playtime_points = 1
    else:
        playtime_points = 0

    conceded_goals_count = _get_player_conceded_goals_count(
        player, match, match_goals, seconds_played, match_player_teams
    )
    conceded_points = _get_conceded_goals_penalty(position, conceded_goals_count)

    total_points = goals_points + assists_points + cs_points + playtime_points + conceded_points

    return {
        'goals': {'count': goals_count, 'points': goals_points},
        'assists': {'count': assists_count, 'points': assists_points},
        'cs': {'count': cs_count, 'points': cs_points},
        'playtime': {'seconds': seconds_played, 'points': playtime_points},
        'conceded_goals': {'count': conceded_goals_count, 'points': conceded_points},
        'total': total_points,
    }


def calculate_total_points(player, match, position, match_goals, match_cs, match_player_teams):
    """Calculate total fantasy points for a player in a match (without breakdown)"""
    result = calculate_match_points(player, match, position, match_goals, match_cs, match_player_teams)
    return result['total']


def calculate_submission_total_points(submission, preloaded_data):
    """Calculate total points for an entire squad submission"""
    tour_matches = preloaded_data.get('tour_matches')
    match_participants = preloaded_data.get('match_participants')
    match_goals = preloaded_data.get('match_goals')
    match_cs = preloaded_data.get('match_cs')
    match_player_teams = preloaded_data.get('match_player_teams')

    total_points = 0
    tour_matches = [match for match in tour_matches if match.numb_tour_id == submission.tour_id]

    for squad_player in submission.squad_players.all():
        player_id = squad_player.player.id
        for match in tour_matches:
            if player_id in match_participants.get(match.id):
                match_points = calculate_match_points(
                    squad_player.player,
                    match,
                    squad_player.position,
                    match_goals.get(match.id, []),
                    match_cs.get(match.id, []),
                    match_player_teams,
                )
                points = match_points['total']

                if submission.captain_player_id == player_id:
                    points *= 2
                if squad_player.squad_type == SquadPlayer.SquadType.BENCH:
                    points *= 0.5
                total_points += points
                break

    return total_points


def calculate_submission_penalty_points(submission):
    """Calculate penalty points for a submission"""
    return submission.penalized_transfers * 15


def calculate_user_total_points(user, tournament, preloaded_data):
    """Calculate total points for a user across all their submissions in a tournament"""

    user_submissions = SquadSubmission.objects.filter(user=user, tournament=tournament).prefetch_related(
        'squad_players__player'
    )

    total_points = 0
    penalty_points = 0

    for submission in user_submissions:
        total_points += calculate_submission_total_points(submission, preloaded_data)
        penalty_points += calculate_submission_penalty_points(submission)

    total_points -= penalty_points

    return {'total_points': total_points, 'penalty_points': penalty_points}


def calculate_player_breakdown(submission, squad_player, preloaded_data):
    """Calculate detailed breakdown for a specific player in a submission"""
    tour_matches = preloaded_data.get('tour_matches')
    match_participants = preloaded_data.get('match_participants')
    match_goals = preloaded_data.get('match_goals')
    match_cs = preloaded_data.get('match_cs')
    match_player_teams = preloaded_data.get('match_player_teams')

    player = squad_player.player

    match_points = {
        'total': 0,
        'goals': {'count': 0, 'points': 0},
        'assists': {'count': 0, 'points': 0},
        'cs': {'count': 0, 'points': 0},
        'conceded_goals': {'count': 0, 'points': 0},
        'playtime': {'seconds': 0, 'points': 0},
    }

    tour_matches = [match for match in tour_matches if match.numb_tour_id == submission.tour_id]
    for match in tour_matches:
        if player.id in match_participants.get(match.id):
            match_points = calculate_match_points(
                player,
                match,
                squad_player.position,
                match_goals.get(match.id, []),
                match_cs.get(match.id, []),
                match_player_teams,
            )
            break

    is_captain = submission.captain_player_id == player.id
    is_bench = squad_player.is_bench_player
    multiplier = 1.0
    if is_captain:
        multiplier = 2.0
    if is_bench:
        multiplier = 0.5

    base_total = match_points['total']
    total_points = base_total * multiplier

    seconds_played = match_points['playtime']['seconds']
    formatted_playtime = f'{seconds_played // 60}:{seconds_played % 60:02d}' if seconds_played > 0 else '—'

    return {
        'total': total_points,
        'items': [
            {'name': 'Время на поле', 'value': formatted_playtime, 'points': match_points['playtime']['points']},
            {'name': 'Голы', 'value': match_points['goals']['count'], 'points': match_points['goals']['points']},
            {
                'name': 'Голевые передачи',
                'value': match_points['assists']['count'],
                'points': match_points['assists']['points'],
            },
            {'name': 'Сухие таймы', 'value': match_points['cs']['count'], 'points': match_points['cs']['points']},
            {
                'name': 'Пропущенные голы',
                'value': match_points['conceded_goals']['count'],
                'points': match_points['conceded_goals']['points'],
            },
        ],
        'multipliers': {'captain': is_captain, 'bench': is_bench, 'multiplier': multiplier},
    }


def _get_player_team_for_match(player, match, match_player_teams):
    """Get player's team for the given match from PlayerMatchStatistics."""
    key = (match.id, player.id)
    return match_player_teams.get(key)


def _count_clean_sheets(player, match, player_team, match_cs):
    """Count clean sheets for a player, only counting those earned in halves when player was on pitch."""
    cs_count = 0
    if player_team:
        intervals = _get_player_intervals(player, match)
        for cs in match_cs:
            if cs.team_id == player_team.id:
                cs_time = cs.time_min * 60 + cs.time_sec
                # Determine which half the clean sheet belongs to
                # First half: 0-8 minutes (0-480 seconds), Second half: 8-16 minutes (480-960 seconds)
                # Clean sheets are typically recorded at the end of a half (8:00 for first, 16:00 for second)
                if cs_time <= 480:
                    half_start, half_end = 0, 480  # First half
                else:
                    half_start, half_end = 481, 960  # Second half
                for start, end in intervals:
                    if start < half_end and end > half_start:
                        cs_count += 1
                        break

    return cs_count


def _get_player_intervals(player, match):
    """Return list of (start_sec, end_sec) intervals when player was on pitch."""
    full_match_seconds = 16 * 60
    if player not in match.match_participants.all():
        return []

    events = []  # (sec, type)
    started = player in match.team_home_start.all() or player in match.team_guest_start.all()
    for subs in match.match_substitutions.all():
        t = subs.time_min * 60 + subs.time_sec
        if subs.player_in_id == player.id:
            events.append((t, 'in'))
        if subs.player_out_id == player.id:
            events.append((t, 'out'))
    events.sort(key=lambda x: x[0])

    intervals = []
    in_play = started
    current_start = 0 if started else None
    for t, kind in events:
        if kind == 'out' and in_play:
            intervals.append((current_start, t))
            in_play = False
            current_start = None
        elif kind == 'in' and not in_play:
            in_play = True
            current_start = t
    if in_play and current_start is not None:
        intervals.append((current_start, full_match_seconds))
    return intervals


def _get_player_playtime(player, match):
    """Get total seconds played by a player in a match"""
    full_match_seconds = 16 * 60
    seconds_played = 0
    if player in match.match_participants.all():
        started = player in match.team_home_start.all() or player in match.team_guest_start.all()
        if started:
            seconds_played = full_match_seconds
        for subs in match.match_substitutions.all():
            if subs.player_in_id == player.id:
                seconds_played += full_match_seconds - (subs.time_min * 60 + subs.time_sec)
            if subs.player_out_id == player.id:
                seconds_played -= full_match_seconds - (subs.time_min * 60 + subs.time_sec)

    return seconds_played


def _get_player_conceded_goals_count(player, match, match_goals, seconds_played, match_player_teams):
    """Get number of conceded goals for a player in a match"""
    conceded_goals_count = 0
    player_team = _get_player_team_for_match(player, match, match_player_teams)
    if seconds_played > 0 and player_team is not None:
        intervals = _get_player_intervals(player, match)
        if intervals:
            opponent_team_id = match.team_guest_id if player_team.id == match.team_home_id else match.team_home_id
            for goal in match_goals:
                if goal.team_id != opponent_team_id:
                    continue
                goal_time = goal.time_min * 60 + goal.time_sec
                for start, end in intervals:
                    if start <= goal_time <= end:
                        conceded_goals_count += 1
                        break
    return conceded_goals_count


def _get_conceded_goals_penalty(position, goals_count):
    """Get penalty points for conceded goals based on position"""
    penalty_ranges = POINTS_CONFIG['conceded_goals']

    for (start, end), penalties in penalty_ranges.items():
        if start <= goals_count <= end:
            return penalties[position]

    return 0
