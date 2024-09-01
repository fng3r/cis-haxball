from core.models import IPAdress, UserActivity
from django.utils import timezone
from django.utils.crypto import get_random_string

from haxball_site import settings

ID_TOKEN_COOKIE_NAME = 'idtoken'


class UserTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)

        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            user_ip = x_forwarded_for.split(',')[0]
        else:
            if not settings.DEBUG:
                user_ip = request.META.get('HTTP_X_REAL_IP')
            else:
                user_ip = request.META.get('REMOTE_ADDR')

        try:
            ip = IPAdress.objects.get(name=request.user, ip=user_ip)
            ip.update = timezone.now()
            ip.save(update_fields=['update'])
        except:
            IPAdress.objects.create(ip=user_ip, name=request.user)

        ips = IPAdress.objects.filter(ip=user_ip)
        if ips.count() > 1:
            for i in ips:
                i.suspicious = True
                i.save(update_fields=['suspicious'])

        user_agent = request.headers['User-Agent']
        user_token = request.COOKIES.get(ID_TOKEN_COOKIE_NAME)
        is_new_user_token = False
        if not user_token:
            is_new_user_token = True
            user_token = get_random_string(length=32)

        response = self.get_response(request)
        if not request.user.is_authenticated:
            return response

        if is_new_user_token:
            response.set_cookie(
                ID_TOKEN_COOKIE_NAME, user_token, samesite='Lax', expires=timezone.now() + timezone.timedelta(days=365)
            )

        try:
            user_activity = UserActivity.objects.get(
                user=request.user, ip=user_ip, user_agent=user_agent, id_token=user_token
            )
            user_activity.last_seen = timezone.now()
            user_activity.save(update_fields=['last_seen'])
        except:
            UserActivity.objects.create(user=request.user, ip=user_ip, user_agent=user_agent, id_token=user_token)

        user_activities = UserActivity.objects.filter(id_token=user_token)
        if user_activities.count() > 1:
            for ua in user_activities:
                ua.has_duplicates = True
                ua.save(update_fields=['has_duplicates'])

        return response
