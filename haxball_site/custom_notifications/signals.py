from core.models import NewComment, Profile
from django.db.models.signals import post_save
from django.dispatch import receiver
from tournament.models import Match

from .utils import notify_comment_reply, notify_match_inspected, notify_profile_comment


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
        
    if isinstance(instance.content_object, Profile) and instance.content_object.name != instance.author and instance.parent is None:
        notify_profile_comment(instance)


@receiver(post_save, sender=Match)
def match_inspected(sender, instance: Match, created, **kwargs):
    """
    Signal handler that is triggered when a match is played.
    This will send a notification if the match is a reply to another match.
    """
    if instance.is_played and instance.tracker.has_changed('is_played'):
        notify_match_inspected(instance)
