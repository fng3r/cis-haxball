import logging
import re

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType

from notifications.signals import notify

from core.models import NewComment
from tournament.models import Disqualification, Match, Team

logger = logging.getLogger('haxball_site')


_notification_actor_cache = {'actor_id': None, 'resolved': False}


def get_notification_actor(fallback=None):
    """Resolve a system actor for automated notifications.

    Prefers the 'admin' superuser (consistent with other notifiers),
    then any staff/superuser, finally the given fallback user.
    Result is cached per process to avoid extra queries in bulk sends.
    """
    if _notification_actor_cache['resolved']:
        actor_id = _notification_actor_cache['actor_id']
        if actor_id is not None:
            try:
                return User.objects.get(id=actor_id)
            except User.DoesNotExist:
                pass
        return fallback

    actor = None
    try:
        actor = User.objects.filter(username='admin').first()
        if actor is None:
            actor = User.objects.filter(is_staff=True).order_by('id').first()
    except Exception as e:
        logger.error(f'Error resolving notification actor: {e}', exc_info=True)

    _notification_actor_cache['actor_id'] = actor.id if actor is not None else None
    _notification_actor_cache['resolved'] = True

    return actor if actor is not None else fallback


def reset_notification_actor_cache():
    """Reset cached notification actor (mainly for tests)."""
    _notification_actor_cache['actor_id'] = None
    _notification_actor_cache['resolved'] = False


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

    logger.debug(f'Sending notification with data: {kwargs}')

    notify.send(
        sender=actor,
        recipient=recipient,
        verb=verb,
        target=target,
        action_object=action_object,
        description=description,
        **kwargs,
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
            verb=f'{comment.author.username} ответил на Ваш комментарий',
            target=parent,
            action_object=comment,
            description=comment.body[:200] + ('...' if len(comment.body) > 200 else ''),
            type='comment_reply',
            url=comment.get_absolute_url(),
            subject_title=str(comment.content_object),
            subject_url=comment.content_object.get_absolute_url(),
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
            verb=f'{comment.author.username} оставил комментарий под Вашим профилем',
            target=comment.content_object,
            action_object=comment,
            description=comment.body[:200] + ('...' if len(comment.body) > 200 else ''),
            type='profile_comment',
            url=comment.get_absolute_url(),
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
            verb=f'{user.username} оценил Ваш пост',
            target=post,
            url=post.get_absolute_url(),
            subject_title=subject_title,
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
        recipients.update(_get_team_executives(match.team_home), _get_team_executives(match.team_guest))
        logger.debug(f'Match inspection notification recipients: {recipients}')
        match_title = f'{match.team_home.short_title} : {match.team_guest.short_title}'

        notify_user(
            recipient=list(recipients),
            actor=actor,
            verb=f'Матч {match_title} c участием Вашей команды был проинспектирован',
            target=match,
            url=match.get_absolute_url(),
            type='match_inspected',
            match_title=match_title,
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
        match_title = (
            f'{disqualification.match.team_home.short_title} : {disqualification.match.team_guest.short_title}'
        )
        disqualified_player = disqualification.player

        notify_user(
            recipient=list(recipients),
            actor=actor,
            verb=f'Игрок Вашей команды ({disqualified_player.nickname}) получил дисквалификацию по итогам матча {match_title}',  # noqa: E501
            action_object=disqualification,
            target=disqualification.match,
            url=disqualification.match.get_absolute_url(),
            type='disqualification',
            match_title=match_title,
            disqualified_player_username=disqualified_player.name.username,
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
            verb=f'{comment.author.username} упомянул Вас в комментарии',
            target=comment.content_object,
            action_object=comment,
            description=comment.body[:200] + ('...' if len(comment.body) > 200 else ''),
            type='user_mention',
            url=comment.get_absolute_url(),
            subject_title=str(comment.content_object),
            subject_url=comment.content_object.get_absolute_url(),
        )
        logger.debug(
            f'User mention notification sent to users: {", ".join([user.username for user in mentioned_users])}'
        )
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


def notify_reward(recipient, amount, tour_number, activity_label, league_title, url=None, actor=None):
    """Send notification about a single-tour reward payout.

    Args:
        recipient: User who received the payout
        amount: Reward amount (Decimal)
        tour_number: Tour number the reward was paid for
        activity_label: Human-readable activity label (e.g. 'фэнтези')
        league_title: League title for context
        url: Optional URL to open on click (defaults to balance page)
        actor: Optional actor User; resolved to system actor when omitted
    """
    try:
        actor = actor or get_notification_actor(fallback=recipient)
        if actor is None:
            logger.error('Cannot send reward notification: no actor available')
            return
        if url is None:
            url = _get_balance_url()

        verb = f'Начислены награды за {tour_number} тур {activity_label}:'
        description = f'Начислено {amount} CC за {tour_number} тур {activity_label} ({league_title}).'

        notify_user(
            recipient=recipient,
            actor=actor,
            verb=verb,
            description=description,
            type='reward',
            url=url,
            amount=str(amount),
            tour_number=tour_number,
            activity_label=activity_label,
            league_title=league_title,
        )
        logger.debug(f'Reward notification sent to {recipient} for tour {tour_number}: +{amount}')
    except Exception as e:
        logger.error(f'Error sending reward notification: {e}', exc_info=True)


def notify_combined_rewards(recipient, total_amount, tour_details, activity_label, league_title, url=None, actor=None):
    """Send a single notification aggregating reward payouts across several tours.

    Args:
        recipient: User who received the payouts
        total_amount: Total reward amount across all tours (Decimal)
        tour_details: Iterable of dicts with keys 'tour_number' and 'amount'
        activity_label: Human-readable activity label (e.g. 'фэнтези')
        league_title: League title for context
        url: Optional URL to open on click (defaults to balance page)
        actor: Optional actor User; resolved to system actor when omitted
    """
    try:
        details = list(tour_details)
        if not details:
            return
        actor = actor or get_notification_actor(fallback=recipient)
        if actor is None:
            logger.error('Cannot send combined reward notification: no actor available')
            return
        if url is None:
            url = _get_balance_url()

        tour_numbers = sorted({item['tour_number'] for item in details})
        if len(tour_numbers) == 1:
            tours_str = f'{tour_numbers[0]} тур'
        else:
            tours_str = f'туры {", ".join(str(n) for n in tour_numbers)}'

        verb = f'Начислены награды {activity_label} ({tours_str}):'
        breakdown = '; '.join(
            f'{item["tour_number"]} тур: +{item["amount"]} CC'
            for item in sorted(details, key=lambda item: item['tour_number'])
        )
        description = f'Начислено {total_amount} CC за {tours_str} {activity_label} ({league_title}). {breakdown}.'

        notify_user(
            recipient=recipient,
            actor=actor,
            verb=verb,
            description=description,
            type='reward',
            url=url,
            amount=str(total_amount),
            tour_numbers=tour_numbers,
            activity_label=activity_label,
            league_title=league_title,
        )
        logger.debug(f'Combined reward notification sent to {recipient}: +{total_amount} for tours {tour_numbers}')
    except Exception as e:
        logger.error(f'Error sending combined reward notification: {e}', exc_info=True)


def notify_gift_received(user_gift):
    """Send notification to the gift recipient (skips self-gifts).

    Args:
        user_gift: UserGift instance that was just granted
    """
    try:
        owner = user_gift.owner
        buyer = user_gift.buyer
        if owner is None or (buyer is not None and owner.id == buyer.id):
            return

        actor = buyer or get_notification_actor(fallback=owner)
        if actor is None:
            logger.error('Cannot send gift notification: no actor available')
            return

        actor_name = buyer.username if buyer is not None else 'Администрация'
        gift_name = user_gift.gift.name
        try:
            profile_url = owner.user_profile.get_absolute_url()
        except Exception:
            profile_url = None

        notify_user(
            recipient=owner,
            actor=actor,
            verb=f'{actor_name} отправил Вам «{gift_name}»',
            target=user_gift.gift,
            action_object=user_gift,
            description=user_gift.message or f'Подарок «{gift_name}» ждёт Вас в профиле.',
            type='gift_received',
            url=profile_url,
            gift_name=gift_name,
        )
        logger.debug(f'Gift notification sent to {owner.username} for gift {gift_name}')
    except Exception as e:
        logger.error(f'Error sending gift notification: {e}', exc_info=True)


def _get_balance_url():
    try:
        from django.urls import reverse

        return reverse('balance:balance')
    except Exception:
        return '/coins/balance/'
