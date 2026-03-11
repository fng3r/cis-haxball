from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import NewComment, Post, Reaction, ReactionType, Subscription
from core.services.reactions import build_reactions_context


class ReactionsFeatureTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(username='author', password='password')
        self.user = User.objects.create_user(username='tester', password='password')
        self.post = Post.objects.create(
            title='Test post',
            author=self.author,
            slug='test-post',
            body='body',
        )
        self.comment = NewComment.objects.create(
            author=self.author,
            body='comment body',
            content_type=ContentType.objects.get_for_model(Post),
            object_id=self.post.id,
        )
        self.client.force_login(self.user)

    def test_widget_get_bootstraps_default_reactions(self):
        self.assertEqual(ReactionType.objects.count(), 0)

        response = self.client.get(reverse('core:reactions', args=['comment', self.comment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertGreater(ReactionType.objects.count(), 0)

    def test_post_reaction_toggle_add_and_remove(self):
        reaction_type = ReactionType.objects.create(code='heart', emoji='❤️', name='Love')
        url = reverse('core:reactions', args=['comment', self.comment.id])

        add_response = self.client.post(url, {'reaction_type': reaction_type.id})
        self.assertEqual(add_response.status_code, 200)
        self.assertEqual(Reaction.objects.count(), 1)

        remove_response = self.client.post(url, {'reaction_type': reaction_type.id})
        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(Reaction.objects.count(), 0)

    def test_post_reaction_appends_different_types(self):
        first = ReactionType.objects.create(code='thumbs_up', emoji='👍', name='Like')
        second = ReactionType.objects.create(code='fire', emoji='🔥', name='Fire')
        url = reverse('core:reactions', args=['comment', self.comment.id])

        self.client.post(url, {'reaction_type': first.id})
        self.client.post(url, {'reaction_type': second.id})

        self.assertEqual(Reaction.objects.count(), 2)
        self.assertTrue(Reaction.objects.filter(reaction_type=first, user=self.user).exists())
        self.assertTrue(Reaction.objects.filter(reaction_type=second, user=self.user).exists())

    def test_reaction_chips_sorted_by_first_reaction_created_time(self):
        first = ReactionType.objects.create(code='first', emoji='😀', name='First')
        second = ReactionType.objects.create(code='second', emoji='🔥', name='Second')

        first_reaction = Reaction.objects.create(
            user=self.user,
            reaction_type=first,
            content_object=self.comment,
        )
        second_reaction = Reaction.objects.create(
            user=self.author,
            reaction_type=second,
            content_object=self.comment,
        )

        now = timezone.now()
        Reaction.objects.filter(pk=first_reaction.pk).update(created=now - timezone.timedelta(minutes=10))
        Reaction.objects.filter(pk=second_reaction.pk).update(created=now - timezone.timedelta(minutes=1))

        context = build_reactions_context(self.comment, self.user)
        ordered_codes = [chip['code'] for chip in context['reaction_chips']]
        self.assertEqual(ordered_codes, ['first', 'second'])

    def test_regular_user_replaces_most_recent_reaction_when_limit_exceeded(self):
        first = ReactionType.objects.create(code='first', emoji='😀', name='First')
        second = ReactionType.objects.create(code='second', emoji='🔥', name='Second')
        url = reverse('core:reactions', args=['comment', self.comment.id])

        self.client.post(url, {'reaction_type': first.id})
        self.client.post(url, {'reaction_type': second.id})

        self.assertFalse(
            Reaction.objects.filter(reaction_type=first, user=self.user, object_id=self.comment.id).exists()
        )
        self.assertTrue(
            Reaction.objects.filter(reaction_type=second, user=self.user, object_id=self.comment.id).exists()
        )
        self.assertEqual(Reaction.objects.filter(user=self.user, object_id=self.comment.id).count(), 1)

    def test_premium_user_can_keep_three_reactions(self):
        reaction_types = [
            ReactionType.objects.create(code=f'code_{index}', emoji='😀', name=f'Name {index}') for index in range(1, 5)
        ]
        Subscription.objects.create(
            user=self.user,
            starts_at=timezone.now() - timezone.timedelta(days=1),
            expires_at=timezone.now() + timezone.timedelta(days=1),
        )
        url = reverse('core:reactions', args=['comment', self.comment.id])

        for reaction_type in reaction_types:
            self.client.post(url, {'reaction_type': reaction_type.id})

        user_reactions = Reaction.objects.filter(user=self.user, object_id=self.comment.id).order_by(
            'reaction_type__code'
        )
        self.assertEqual(user_reactions.count(), 3)
        self.assertEqual(
            list(user_reactions.values_list('reaction_type__code', flat=True)),
            ['code_2', 'code_3', 'code_4'],
        )

    def test_superuser_has_unlimited_reactions(self):
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        reaction_types = [
            ReactionType.objects.create(code=f'super_{index}', emoji='😀', name=f'Super {index}')
            for index in range(1, 6)
        ]
        url = reverse('core:reactions', args=['comment', self.comment.id])

        for reaction_type in reaction_types:
            self.client.post(url, {'reaction_type': reaction_type.id})

        self.assertEqual(Reaction.objects.filter(user=self.user, object_id=self.comment.id).count(), 5)
