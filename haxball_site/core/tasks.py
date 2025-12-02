from celery import shared_task

from core.models import Subscription, UserIcon


@shared_task
def sync_user_icons():
    """
    Bi-directional sync of premium icons with user subscriptions.

    - Grants premium icon to users with active subscriptions but no icon
    - Removes premium icon from users without active subscriptions but with icon
    """
    premium_icon = UserIcon.objects.filter(title='Premium Star').first()
    if not premium_icon:
        return {'error': 'Premium Star icon not found'}

    active_subscriptions = Subscription.objects.active().select_related('user').exclude(user__isnull=True)
    users_with_active_subscription = {sub.user for sub in active_subscriptions}

    profiles_with_icon = premium_icon.user.all()
    users_with_icon = {profile.name for profile in profiles_with_icon if profile.name}

    users_to_grant = users_with_active_subscription - users_with_icon
    granted_users = []
    for user in users_to_grant:
        premium_icon.user.add(user.user_profile)
        granted_users.append(
            {
                'id': user.id,
                'username': user.username,
            }
        )

    users_to_revoke = users_with_icon - users_with_active_subscription
    revoked_users = []
    for user in users_to_revoke:
        premium_icon.user.remove(user.user_profile)
        revoked_users.append(
            {
                'id': user.id,
                'username': user.username,
            }
        )

    return {
        'granted': {
            'count': len(granted_users),
            'users': granted_users,
        },
        'revoked': {
            'count': len(revoked_users),
            'users': revoked_users,
        },
    }
