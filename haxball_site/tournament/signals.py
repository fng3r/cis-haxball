from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import AwardSubmission, AwardVote, Match, MatchSeries
from .tasks import fetch_match_replay_stats


@receiver(post_save, sender=AwardVote)
def award_vote_saved(sender, instance, **kwargs):
    """Recalculate results when a vote is saved"""
    instance.award.recalculate_results()


@receiver(post_delete, sender=AwardVote)
def award_vote_deleted(sender, instance, **kwargs):
    """Recalculate results when a vote is deleted"""
    instance.award.recalculate_results()


@receiver(post_save, sender=AwardSubmission)
def award_submission_submitted(sender, instance, **kwargs):
    """Recalculate results for all awards in the campaign when voting is submitted"""
    from .models import Award

    awards = Award.objects.filter(campaign=instance.campaign)
    for award in awards:
        award.recalculate_results()


@receiver(post_delete, sender=AwardSubmission)
def award_submission_deleted(sender, instance, **kwargs):
    """Recalculate results for all awards in the campaign when a submission is deleted"""
    from .models import Award

    awards = Award.objects.filter(campaign=instance.campaign)
    for award in awards:
        award.recalculate_results()


@receiver(post_save, sender=Match)
def schedule_fetch_match_replay_stats(sender, instance, **kwargs):
    """When Match.replays changes, schedule Celery task to fetch stats."""
    if not instance.tracker.has_changed('replays'):
        return

    transaction.on_commit(lambda: fetch_match_replay_stats.delay(instance.pk))


def link_match_to_series(match):
    """Create or link a match to its playoff series."""
    if not match.bracket_slot or match.numb_tour is None:
        return

    series = MatchSeries.objects.filter(
        tour=match.numb_tour,
        bracket_slot=match.bracket_slot,
    ).first()

    if series is None:
        series = MatchSeries.objects.create(
            tour=match.numb_tour,
            bracket_slot=match.bracket_slot,
            team_home=match.team_home,
            team_guest=match.team_guest,
        )

    if match.series_id != series.id:
        match.series = series
        Match.objects.filter(id=match.id).update(series=series)


@receiver(post_save, sender=Match)
def auto_link_match_to_series(sender, instance, **kwargs):
    """When a playoff match is saved, ensure it belongs to its series."""
    if not instance.bracket_slot or instance.stage_id is None:
        return

    link_match_to_series(instance)
