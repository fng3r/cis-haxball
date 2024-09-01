"""haxball_site URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from ckeditor_uploader import views as ckuploader_views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path, re_path
from django.views.decorators.cache import never_cache

urlpatterns = [
    path('grappelli/', include('grappelli.urls')),
    path('admin/', admin.site.urls),
    re_path(r'^ckeditor/upload/', login_required(ckuploader_views.upload), name='ckeditor_upload'),
    re_path(r'^ckeditor/browse/', never_cache(login_required(ckuploader_views.browse)), name='ckeditor_browse'),
    path('chaining/', include('smart_selects.urls')),
    path('', include('core.urls', namespace='core')),
    path('championship/', include('tournament.urls', namespace='tournament')),
    path('host_reservation/', include('reservation.urls', namespace='reservation')),
    path('polls/', include('polls.urls', namespace='polls')),
    path('accounts/', include('allauth.urls')),
    path('summernote/', include('django_summernote.urls')),
    path('__debug__/', include('debug_toolbar.urls')),
]

if settings.URL_PREFIX:
    urlpatterns = [path(settings.URL_PREFIX, include(urlpatterns))]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
