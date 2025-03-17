import logging

from core.models import NewComment
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from notifications.signals import notify
from tournament.models import Disqualification, Match

# Get a logger for this module
logger = logging.getLogger('haxball_site.notificationsa')


def notify_user(recipient, actor, verb, target=None, action_object=None, description=None, **kwargs):
    """
    Send a notification to a user.
    
    Args:
        recipient: User or list of Users who will receive the notification
        actor: User who performed the action
        verb: Description of the action
        target: Optional target of the action
        action_object: Optional object of the action
        description: Optional detailed description
        url: Optional URL to redirect to when clicked
        **kwargs: Additional data to store with the notification
    """
    
    logger.debug(f"Sending notification with data: {kwargs}")
    
    notify.send(
        sender=actor,
        recipient=recipient,
        verb=verb,
        target=target,
        action_object=action_object,
        description=description,
        **kwargs
    )


def notify_comment_reply(comment: NewComment):
    """
    Send notification when a user replies to a comment.
    """
    try:
        parent = comment.parent
        notify_user(
            recipient=parent.author,
            actor=comment.author,
            verb=f"{comment.author.username} ответил на ваш комментарий",
            target=parent,
            action_object=comment,
            description=comment.body[:200] + ('...' if len(comment.body) > 200 else ''),
            type='comment_reply',
            url=comment.get_absolute_url(),
            subject_title=str(comment.content_object),
            subject_url=comment.content_object.get_absolute_url()
        )
        logger.debug('Comment reply notification sent')
    except Exception as e:
        logger.error(f'Error sending comment reply notification: {e}', exc_info=True)

    
def notify_profile_comment(comment: NewComment):
    """
    Send notification when a user comments on a profile.
    """
    try:
        notify_user(
            recipient=comment.content_object.name,
            actor=comment.author,
        verb=f"{comment.author.username} оставил комментарий под Вашим профилем",
        target=comment.content_object,
        action_object=comment,
        description=comment.body[:200] + ('...' if len(comment.body) > 200 else ''),
            type='profile_comment',
            url=comment.get_absolute_url()
        )
        logger.debug('Profile comment notification sent')
    except Exception as e:
        logger.error(f'Error sending profile comment notification: {e}', exc_info=True)
    
def notify_like(user, post):
    """
    Send notification when a user likes a post.
    """
    try:
        if post.author != user:
            subject_title = None
            content_type = ContentType.objects.get_for_model(post)
        
        if content_type.model == 'post':
            subject_title = post.title
        
        notify_user(
            recipient=post.author,
            actor=user,
            verb=f"{user.username} оценил ваш пост",
            target=post,
            url=post.get_absolute_url(),
            subject_title=subject_title
        )
        logger.debug('Like notification sent')
    except Exception as e:
        logger.error(f'Error sending like notification: {e}', exc_info=True)


def notify_match_inspected(match: Match):
    """
    Send notification when a match is inspected.
    """
    try:
        actor = match.inspector or User.objects.get(username='admin')
        recipients = set((match.team_home.owner, match.team_guest.owner))
        all_players = match.team_home.players_in_team.all() | match.team_guest.players_in_team.all()
        for player in all_players:
            if player.role == 'C' or player.role == 'AC':
                recipients.add(player.name)
        logger.debug(f'Match inspection notification recipients: {recipients}')
        match_title = f'{match.team_home.short_title} : {match.team_guest.short_title}'
        
        notify_user(
            recipient=list(recipients),
            actor=actor,
            verb=f'Матч {match_title} c участием Вашей команды был проинспектирован',
            target=match,
            url=match.get_absolute_url(),
            type='match_inspected',
            match_title=match_title
        )
        logger.debug(f'Match inspected notification sent for match {match_title}')
    except Exception as e:
        logger.error(f'Error sending match inspected notification: {e}', exc_info=True)
    

def notify_disqualification(disqualification: Disqualification):
    """
    Send notification when a disqualification is created.
    """
    try:
        actor = disqualification.match.inspector or User.objects.get(username='admin')
        recipients = set((disqualification.team.owner, disqualification.player.name))
        for player in disqualification.team.players_in_team.all():
            if player.role == 'C' or player.role == 'AC':
                recipients.add(player.name)
        logger.debug(f'Disqualification notification recipients: {recipients}')
        match_title = f'{disqualification.match.team_home.short_title} : {disqualification.match.team_guest.short_title}'
        disqualified_player = disqualification.player
        
        notify_user(
            recipient=list(recipients),
            actor=actor,
            verb=f'Игрок Вашей команды ({disqualified_player.nickname}) получил дисквалификацию по итогам матча {match_title}',
            action_object=disqualification,
            target=disqualification.match,
            url=disqualification.match.get_absolute_url(),
            type='disqualification',
            match_title=match_title,
            disqualified_player_username=disqualified_player.name.username
        )
        logger.debug(f'Disqualification notification sent for player {disqualified_player.nickname} in match {match_title}')
    except Exception as e:
        logger.error(f'Error sending disqualification notification: {e}', exc_info=True)