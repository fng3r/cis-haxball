from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import NewComment, Profile
from tournament.models import Disqualification, Match

from .notifications import (
    notify_comment_reply,
    notify_disqualification,
    notify_match_inspected,
    notify_profile_comment,
    notify_user_mention,
)


@receiver(post_save, sender=NewComment)
def comment_created(sender, instance: NewComment, created, **kwargs):
    """
    Signal handler that is triggered when a comment is created.
    This will send a notification if the comment is a reply to another comment.
    """
    if not created:
        return

    if instance.parent and instance.parent.author != instance.author:
        notify_comment_reply(instance)

    if (
        isinstance(instance.content_object, Profile)
        and instance.content_object.name != instance.author
        and instance.parent is None
    ):
        notify_profile_comment(instance)

    notify_user_mention(instance)


@receiver(post_save, sender=Match)
def match_inspected(sender, instance: Match, created, **kwargs):
    """
    Signal handler that is triggered when a match is played.
    This will send a notification to all team's staff members.
    """
    if instance.is_played and instance.tracker.has_changed('is_played'):
        notify_match_inspected(instance)


@receiver(post_save, sender=Disqualification)
def disqualification_created(sender, instance: Disqualification, created, **kwargs):
    """
    Signal handler that is triggered when a disqualification is created.
    This will send a notification to all team's staff members.
    """
    if not created:
        return

    notify_disqualification(instance)
