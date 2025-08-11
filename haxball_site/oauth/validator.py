from django.urls import reverse

from oauth2_provider.oauth2_validators import OAuth2Validator

from haxball_site.settings import BASE_URL


class CustomOIDCValidator(OAuth2Validator):
    def get_additional_claims(self, request):
        """
        Add custom claims to the OIDC ID token.
        """
        user = request.user

        return {
            'preferred_username': user.username,
            'profile': BASE_URL
            + reverse('core:profile_detail', kwargs={'pk': user.user_profile.pk, 'slug': user.user_profile.slug}),
        }
