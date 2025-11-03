from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from balance.models import ShopItem, ShopPurchase
from balance.services.balance import BalanceService
from core.models import NewComment, Post, Subscription, UserIcon


class ShopService:
    """Service layer for shop operations"""

    @staticmethod
    def purchase_item(user: User, item: ShopItem, metadata: dict[str, object] | None = None) -> ShopPurchase:
        if not item.is_active:
            raise ValidationError('Этот товар недоступен для покупки')

        if metadata is None:
            metadata = {}

        with transaction.atomic():
            transaction_obj = BalanceService.subtract_coins(
                user=user,
                amount=item.price,
                description=f'Покупка: {item.name}',
            )

            subscription = None
            purchase_metadata: dict[str, object] = {}

            if item.product_type == ShopItem.ProductType.SUBSCRIPTION:
                subscription = ShopService._activate_subscription(user, item)
                purchase_metadata = {
                    'subscription_id': subscription.id,
                    'starts_at': subscription.starts_at.isoformat(),
                    'expires_at': subscription.expires_at.isoformat(),
                    'tier': subscription.tier,
                }
            elif item.product_type == ShopItem.ProductType.CHANGE_USERNAME:
                new_username = metadata.get('new_username')
                if not new_username:
                    raise ValidationError('Необходимо указать новое имя пользователя')
                purchase_metadata = {
                    'old_username': user.username,
                    'new_username': new_username,
                }
            elif item.product_type == ShopItem.ProductType.CHANGE_PUBLIC_ID:
                new_public_id = metadata.get('new_public_id')
                if not new_public_id:
                    raise ValidationError('Необходимо указать новый публичный ID')
                purchase_metadata = {
                    'new_public_id': new_public_id,
                }

            purchase = ShopPurchase.objects.create(
                user=user,
                item=item,
                amount=item.price,
                transaction=transaction_obj,
                metadata=purchase_metadata,
            )

            if item.product_type in [ShopItem.ProductType.CHANGE_USERNAME, ShopItem.ProductType.CHANGE_PUBLIC_ID]:
                comment = ShopService._create_service_comment(user, item, purchase, purchase_metadata)
                if comment:
                    purchase_metadata['comment_id'] = comment.id

            if 'comment_id' in purchase_metadata:
                purchase.metadata = purchase_metadata
                purchase.save(update_fields=['metadata'])

            return purchase

    @staticmethod
    def _create_service_comment(
        user: User, item: ShopItem, purchase: ShopPurchase, metadata: dict[str, object]
    ) -> NewComment | None:
        """Create an auto-generated comment on the special org post"""
        try:
            org_post = Post.objects.get(id=111, slug='org_razdel')
        except Post.DoesNotExist:
            try:
                org_post = Post.objects.get(id=111)
            except Post.DoesNotExist:
                return None

        content_type = ContentType.objects.get_for_model(Post)

        if item.product_type == ShopItem.ProductType.CHANGE_USERNAME:
            template_name = 'balance/comments/username_change_comment.html'
            context = {
                'old_username': metadata.get('old_username'),
                'new_username': metadata.get('new_username'),
            }
        elif item.product_type == ShopItem.ProductType.CHANGE_PUBLIC_ID:
            template_name = 'balance/comments/public_id_change_comment.html'
            context = {
                'new_public_id': metadata.get('new_public_id'),
            }
        else:
            return None

        comment_body = render_to_string(template_name, context)

        comment = NewComment.objects.create(
            content_type=content_type,
            object_id=org_post.id,
            author=user,
            body=comment_body,
            purchase=purchase,
        )
        return comment

    @staticmethod
    def _activate_subscription(user: User, item: ShopItem) -> Subscription:
        tier = item.subscription_tier or Subscription.TIER_1
        duration_in_days = item.subscription_duration_in_days or 30

        now = timezone.now()
        latest_subscription = Subscription.objects.by_user(user).filter(disabled=False).order_by('-expires_at').first()

        if latest_subscription and latest_subscription.expires_at > now:
            starts_at = latest_subscription.expires_at
        else:
            starts_at = now

        expires_at = starts_at + timedelta(days=duration_in_days)

        subscription = Subscription.objects.create(
            user=user,
            tier=tier,
            starts_at=starts_at,
            expires_at=expires_at,
            disabled=False,
        )

        ShopService._grant_premium_icon(user)

        return subscription

    @staticmethod
    def _grant_premium_icon(user: User) -> None:
        profile = user.user_profile
        icon = UserIcon.objects.filter(title='Premium Star').first()
        if not icon:
            return

        icon.user.add(profile)
