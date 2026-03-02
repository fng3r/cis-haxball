from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Post, Reaction, ReactionType


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
        self.client.force_login(self.user)

    def test_widget_get_bootstraps_default_reactions(self):
        self.assertEqual(ReactionType.objects.count(), 0)

        response = self.client.get(reverse('core:reactions', args=['post', self.post.id]))

        self.assertEqual(response.status_code, 200)
        self.assertGreater(ReactionType.objects.count(), 0)

    def test_post_reaction_toggle_add_and_remove(self):
        reaction_type = ReactionType.objects.create(
            code='heart', emoji='❤️', label='Love', sort_order=10, is_active=True
        )
        url = reverse('core:reactions', args=['post', self.post.id])

        add_response = self.client.post(url, {'reaction_type': reaction_type.id})
        self.assertEqual(add_response.status_code, 200)
        self.assertEqual(Reaction.objects.count(), 1)

        remove_response = self.client.post(url, {'reaction_type': reaction_type.id})
        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(Reaction.objects.count(), 0)

    def test_post_reaction_appends_different_types(self):
        first = ReactionType.objects.create(code='thumbs_up', emoji='👍', label='Like', sort_order=10, is_active=True)
        second = ReactionType.objects.create(code='fire', emoji='🔥', label='Fire', sort_order=20, is_active=True)
        url = reverse('core:reactions', args=['post', self.post.id])

        self.client.post(url, {'reaction_type': first.id})
        self.client.post(url, {'reaction_type': second.id})

        self.assertEqual(Reaction.objects.count(), 2)
        self.assertTrue(Reaction.objects.filter(reaction_type=first, user=self.user).exists())
        self.assertTrue(Reaction.objects.filter(reaction_type=second, user=self.user).exists())
