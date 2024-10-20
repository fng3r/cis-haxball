"""
Django settings for haxball_site project.

Generated by 'django-admin startproject' using Django 3.0.8.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.0/ref/settings/
"""

import os

from decouple import config
from django.contrib.messages import constants as messages

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('APP_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('APP_DEBUG', cast=bool, default=False)

ALLOWED_HOSTS = config('APP_ALLOWED_HOSTS', cast=str.split)

# Application definition

INSTALLED_APPS = [
    'template_partials',
    'core.apps.CoreConfig',
    'tournament.apps.TournamentConfig',
    'polls.apps.PollsConfig',
    'reservation.apps.ReservationConfig',
    'django_filters',
    'smart_selects',
    'grappelli',
    'colorfield',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'online_users',
    'allauth',
    'allauth.account',
    'ckeditor',
    'django_summernote',
    'froala_editor',
    'ckeditor_uploader',
    'sorl.thumbnail',
    'mathfilters',
    'debug_toolbar',
    'django_extensions',
    'django_htmx',
    'widget_tweaks',
    'polymorphic',
]

MIDDLEWARE = [
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'haxball_site.middleware.UserTrackingMiddleware',
    'online_users.middleware.OnlineNowMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'haxball_site.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'haxball_site.context_processors.running_line_context',
            ],
            'builtins': ['template_partials.templatetags.partials'],
        },
    },
]

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

WSGI_APPLICATION = 'haxball_site.wsgi.application'

USE_DJANGO_JQUERY = True
# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

X_FRAME_OPTIONS = 'SAMEORIGIN'

# if DEBUG:
#     DATABASES = {
#         'default': {
#             'ENGINE': 'django.db.backends.sqlite3',
#             'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
#             'OPTIONS': {'timeout': 30},
#         }
#     }
# else:
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT'),
    }
}

AUTHENTICATION_BACKENDS = [
    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',
    # `allauth` specific authentication methods, such as login by e-mail
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = 'ru'

TIME_ZONE = 'Europe/Moscow'

USE_TZ = True

USE_I18N = True

USE_L10N = True

if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    # ACCOUNT_EMAIL_REQUIRED = True
    # ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 1
    # ACCOUNT_EMAIL_VERIFICATION = True
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    ACCOUNT_EMAIL_REQUIRED = True
    ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 1
    ACCOUNT_EMAIL_VERIFICATION = True

if DEBUG:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
            'LOCATION': os.path.join(BASE_DIR, 'mycache'),
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
            'LOCATION': '/var/tmp/django_cache',
        }
    }

EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT', cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', cast=bool, default=True)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

if DEBUG:
    STATIC_URL = config('APP_STATIC_URL', default='/static/')
    STATIC_DIR = os.path.join(BASE_DIR, 'static')
    STATICFILES_DIRS = [STATIC_DIR]
    MEDIA_URL = '/media/'
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
else:
    STATIC_ROOT = os.path.join(BASE_DIR, 'static')
    STATIC_URL = config('APP_STATIC_URL', default='/static/')
    MEDIA_URL = '/media/'
    MEDIA_ROOT = '/home/site/media'

CKEDITOR_UPLOAD_PATH = 'uploads/'

LOGIN_REDIRECT_URL = '/'
ACCOUNT_LOGOUT_REDIRECT_URL = '/'

SITE_ID = 1

URL_PREFIX = config('APP_URL_PREFIX', default='')

EDIT_COMMENT_TIME_LIMIT = config('APP_EDIT_COMMENT_TIME_LIMIT', cast=int, default=180)
EDIT_COMMENT_LIMIT = config('APP_EDIT_COMMENT_LIMIT', cast=int, default=5)

# Grapelli config
GRAPPELLI_ADMIN_TITLE = 'Место уважаемых администраторов'

# text-editors config
SUMMERNOTE_THEME = 'bs4'

SUMMERNOTE_CONFIG = {
    'iframe': True,
    'summernote': {
        'airMode': False,
        'width': '100%',
        'height': '200',
        'js': {},
        'codemirror': {
            'mode': 'htmlmixed',
            'lineNumbers': 'true',
            # You have to include theme file in 'css' or 'css_for_inplace' before using it.
            'theme': 'monokai',
        },
        'toolbar': [
            ['font', ['bold', 'underline', 'clear']],
            ['insert', ['link', 'picture', 'video']],
        ],
    },
    'js': ('/static/summernote-ext-print.js',),
    'js_for_inplace': ('/static/summernote-ext-print.js',),
    'css': ('//cdnjs.cloudflare.com/ajax/libs/codemirror/5.40.0/theme/base16-dark.min.css',),
    'css_for_inplace': ('//cdnjs.cloudflare.com/ajax/libs/codemirror/5.40.0/theme/base16-dark.min.css',),
    'codemirror': {
        'theme': 'base16-dark',
        'mode': 'htmlmixed',
        'lineNumbers': 'true',
    },
    'lazy': False,
}

CKEDITOR_CONFIGS = {
    'default': {
        'skin': 'moono',
        'height': 400,
        'width': '100%',
        'toolbar_Basic': [['Source', '-', 'Bold', 'Italic']],
        'toolbar_YourCustomToolbarConfig': [
            {'name': 'document', 'items': ['Source', '-', 'Save', 'NewPage', 'Preview', 'Print', '-', 'Templates']},
            {'name': 'clipboard', 'items': ['Cut', 'Copy', 'Paste', 'PasteText', 'PasteFromWord', '-', 'Undo', 'Redo']},
            {'name': 'editing', 'items': ['Find', 'Replace', '-', 'SelectAll']},
            {
                'name': 'forms',
                'items': [
                    'Form',
                    'Checkbox',
                    'Radio',
                    'TextField',
                    'Textarea',
                    'Select',
                    'Button',
                    'ImageButton',
                    'HiddenField',
                ],
            },
            '/',
            {
                'name': 'basicstyles',
                'items': ['Bold', 'Italic', 'Underline', 'Strike', 'Subscript', 'Superscript', '-', 'RemoveFormat'],
            },
            {
                'name': 'paragraph',
                'items': [
                    'NumberedList',
                    'BulletedList',
                    '-',
                    'Outdent',
                    'Indent',
                    '-',
                    'Blockquote',
                    'CreateDiv',
                    '-',
                    'JustifyLeft',
                    'JustifyCenter',
                    'JustifyRight',
                    'JustifyBlock',
                    '-',
                    'BidiLtr',
                    'BidiRtl',
                    'Language',
                ],
            },
            {'name': 'links', 'items': ['Link', 'Unlink', 'Anchor']},
            {
                'name': 'insert',
                'items': ['Image', 'Flash', 'Table', 'HorizontalRule', 'Smiley', 'SpecialChar', 'PageBreak', 'Iframe'],
            },
            '/',
            {'name': 'styles', 'items': ['Styles', 'Format', 'Font', 'FontSize']},
            {'name': 'colors', 'items': ['TextColor', 'BGColor']},
            {'name': 'tools', 'items': ['Maximize', 'ShowBlocks']},
            {'name': 'about', 'items': ['About', 'Spoiler']},
            '/',  # put this to force next toolbar on new line
            {
                'name': 'yourcustomtools',
                'items': [
                    # put the name of your editor.ui.addButton here
                    'Preview',
                    'Maximize',
                    'Youtube',
                ],
            },
        ],
        'toolbar': 'YourCustomToolbarConfig',  # put selected toolbar config here
        'tabSpaces': 4,
        'extraPlugins': ','.join(
            [
                'uploadimage',
                'div',
                'autolink',
                'autoembed',
                'embedsemantic',
                'autogrow',
                'spoiler',
                'widget',
                'lineutils',
                'clipboard',
                'dialog',
                'dialogui',
                'elementspath',
                'youtube',
            ]
        ),
    },
    'comment': {
        'skin': 'moono-lisa',
        'removePlugins': 'stylesheetparser',
        'allowedContent': True,
        'height': 200,
        'width': '99%',
        'toolbar': [
            [
                'Bold',
                'Italic',
                'Underline',
                'Strike',
                '-',
                'Link',
                'Unlink',
                'Image',
                'Youtube',
                'Html5video',
                'Smiley',
                '-',
                'NumberedList',
                'BulletedList',
                '-',
                'Undo',
                'Redo',
            ]
        ],
        'extraPlugins': [
                'uploadimage',
                'div',
                'autolink',
                'embedsemantic',
                'autogrow',
                'widget',
                'lineutils',
                'clipboard',
                'dialog',
                'dialogui',
                'elementspath',
                'youtube',
                'html5video',
        ]
    },
}

INTERNAL_IPS = config('INTERNAL_IPS', cast=str.split)

# This sets the mapping of message level to message tag, which is typically rendered as a CSS class in HTML.
# https://docs.djangoproject.com/en/4.2/ref/settings/#message-tags
# Customize tags with bootstrap alert classes
MESSAGE_TAGS = {
    messages.DEBUG: "alert-secondary",
    messages.INFO: "alert-primary",
    messages.SUCCESS: "alert-success",
    messages.WARNING: "alert-warning",
    messages.ERROR: "alert-danger",
}
