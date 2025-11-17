from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import AwardSubmission, AwardVote


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
