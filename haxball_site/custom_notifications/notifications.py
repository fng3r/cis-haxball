import logging
import re

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType

from notifications.signals import notify

from core.models import NewComment
from tournament.models import Disqualification, Match, Team

logger = logging.getLogger('haxball_site')


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
            verb=f"{comment.author.username} ответил на Ваш комментарий",
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
            verb=f"{user.username} оценил Ваш пост",
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
        recipients = set()
        recipients.update(
            _get_team_executives(match.team_home),
            _get_team_executives(match.team_guest)
        )
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
        recipients = set()
        recipients.add(disqualification.player.name)
        recipients.update(_get_team_executives(disqualification.team))
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
        logger.debug('Disqualification notification sent')
    except Exception as e:
        logger.error(f'Error sending disqualification notification: {e}', exc_info=True)


def notify_user_mention(comment: NewComment):
    """
    Send notification when a user is mentioned in a comment.
    
    Args:
        comment: The comment containing the mention
        mentioned_user: The user who was mentioned
    """
    try:
        mentioned_users = _parse_mentions(comment)
        
        notify_user(
            recipient=list(mentioned_users),
            actor=comment.author,
            verb=f"{comment.author.username} упомянул Вас в комментарии",
            target=comment.content_object,
            action_object=comment,
            description=comment.body[:200] + ('...' if len(comment.body) > 200 else ''),
            type='user_mention',
            url=comment.get_absolute_url(),
            subject_title=str(comment.content_object),
            subject_url=comment.content_object.get_absolute_url()
        )
        logger.debug(f'User mention notification sent to users: {", ".join([user.username for user in mentioned_users])}')
    except Exception as e:
        logger.error(f'Error sending user mention notification: {e}', exc_info=True)
        
        
def _parse_mentions(comment: NewComment):
    """
    Parse a comment for user mentions and send notifications to mentioned users.
    
    Args:
        comment: The comment to parse for mentions
    """
    # Find all data-mentioned-user-id attributes in the comment body
    # This regex looks for data-mentioned-user-id="123" pattern
    mention_pattern = r'data-mentioned-user-id="(\d+)"'
    mentioned_user_ids = re.findall(mention_pattern, comment.body)
    
    if not mentioned_user_ids:
        return []
    
    mentioned_user_ids = set(int(user_id) for user_id in mentioned_user_ids)

    return User.objects.filter(id__in=mentioned_user_ids).exclude(id=comment.author.id)


def _get_team_executives(team: Team):
    result = set()
    result.add(team.owner)
    if team.captain is not None:
        result.add(team.captain.name)
    if team.captain_assistant is not None:
        result.add(team.captain_assistant.name)
        
    return result