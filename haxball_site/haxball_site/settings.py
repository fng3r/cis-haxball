import os

from django.contrib.messages import constants as messages
from django.templatetags.static import static
from django.urls import reverse_lazy

from decouple import config

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('APP_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('APP_DEBUG', cast=bool, default=False)

ALLOWED_HOSTS = config('APP_ALLOWED_HOSTS', cast=str.split)

INSTALLED_APPS = [
    'template_partials',
    'online_users',
    'notifications',
    'django_filters',
    'smart_selects',
    'colorfield',
    'unfold',
    'unfold.contrib.filters',
    'unfold.contrib.forms',
    'unfold.contrib.inlines',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.humanize',
    'oauth2_provider',
    'allauth',
    'allauth.account',
    'core.apps.CoreConfig',
    'tournament.apps.TournamentConfig',
    'polls.apps.PollsConfig',
    'reservation.apps.ReservationConfig',
    'utils.apps.UtilsConfig',
    'custom_notifications.apps.CustomNotificationsConfig',
    'oauth.apps.OauthConfig',
    'predictions.apps.PredictionsConfig',
    'fantasy_league.apps.FantasyLeagueConfig',
    'balance.apps.BalanceConfig',
    'ckeditor',
    'django_summernote',
    'ckeditor_uploader',
    'sorl.thumbnail',
    'mathfilters',
    'debug_toolbar',
    'django_extensions',
    'django_htmx',
    'widget_tweaks',
    'polymorphic',
    'django_vite',
]

MIDDLEWARE = [
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'oauth2_provider.middleware.OAuth2TokenMiddleware',
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
                'haxball_site.context_processors.latest_matches_context',
                'haxball_site.context_processors.upcoming_matches_context',
                'haxball_site.context_processors.online_users_context',
                'haxball_site.context_processors.notifications_context',
                'haxball_site.context_processors.youtube_context',
                'haxball_site.context_processors.themes_context',
                'haxball_site.context_processors.settings_context',
            ],
            'builtins': ['template_partials.templatetags.partials'],
        },
    },
]

# Notification settings
DJANGO_NOTIFICATIONS_CONFIG = {'USE_JSONFIELD': True}

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

WSGI_APPLICATION = 'haxball_site.wsgi.application'

USE_DJANGO_JQUERY = True

X_FRAME_OPTIONS = 'SAMEORIGIN'

# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases
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
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    ACCOUNT_EMAIL_REQUIRED = True
    ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 1
    ACCOUNT_EMAIL_VERIFICATION = True

if DEBUG:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
            'LOCATION': config('CACHE_LOCATION', default=os.path.join(BASE_DIR, '.site_cache')),
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
            'LOCATION': config('CACHE_LOCATION', default='/var/tmp/django_cache'),
        }
    }

EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT', cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', cast=bool, default=True)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

STATIC_URL = config('APP_STATIC_URL', default='/static/')
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

MEDIA_URL = '/media/'
if DEBUG:
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
else:
    MEDIA_ROOT = '/home/site/media'

DJANGO_VITE = {
    'default': {
        'dev_mode': DEBUG,
        # rm this setting when static files will be served from STATIC_ROOT directory in production
        'manifest_path': os.path.join(BASE_DIR, 'static', 'manifest.json'),
    }
}

CKEDITOR_UPLOAD_PATH = 'uploads/'

LOGIN_REDIRECT_URL = '/'
ACCOUNT_LOGOUT_REDIRECT_URL = '/'

SITE_ID = 1

URL_PREFIX = config('APP_URL_PREFIX', default='')
BASE_URL = config('APP_BASE_URL')

DELETE_COMMENT_TIME_LIMIT = config('APP_DELETE_COMMENT_TIME_LIMIT', default=60)
EDIT_COMMENT_TIME_LIMIT = config('APP_EDIT_COMMENT_TIME_LIMIT', cast=int, default=180)
EDIT_COMMENT_LIMIT = config('APP_EDIT_COMMENT_LIMIT', cast=int, default=5)

SHOW_USER_TEAM_ICONS = config('APP_SHOW_USER_TEAM_ICONS', cast=bool, default=True)

SHOW_PLAYERS_RATING_BANNER = config('APP_SHOW_PLAYERS_RATING_BANNER', cast=bool, default=False)
SHOW_FREE_AGENTS_BANNER = config('APP_SHOW_FREE_AGENTS_BANNER', cast=bool, default=False)

ACTIVITIES_CURRENT_TOUR = config('APP_ACTIVITIES_CURRENT_TOUR', cast=int, default=1)
ACTIVITIES_BADGE_LABEL = config('APP_ACTIVITIES_BADGE_LABEL')

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
            {'name': 'styles', 'items': ['Styles', 'Format', 'Font', 'FontSize']},
            {'name': 'colors', 'items': ['TextColor', 'BGColor']},
            '/',
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
                'items': [
                    'EmojiPanel',
                    'Image',
                    'Youtube',
                    'Html5video',
                    'Table',
                    'HorizontalRule',
                    'SpecialChar',
                    'PageBreak',
                    'Iframe',
                    'Spoiler',
                ],
            },
            '/',
            {'name': 'tools', 'items': ['Maximize', 'ShowBlocks', 'Preview']},
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
                'html5video',
                'emoji',
                'autocomplete',
                'textwatcher',
                'textmatch',
                'image2',
                'mentions',
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
                'EmojiPanel',
                '-',
                'NumberedList',
                'BulletedList',
                '-',
                'Undo',
                'Redo',
            ]
        ],
        'extraPlugins': ','.join(
            [
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
                'emoji',
                'autocomplete',
                'textwatcher',
                'textmatch',
                'editorplaceholder',
                'image2',
                'mentions',
            ]
        ),
        'editorplaceholder': 'Введите текст комментария...',
        'editorplaceholder_delay': 200,
        'mentions': [
            {
                'feed': '/api/users/search?query={encodedQuery}',
                'marker': '@',
                'minChars': 1,
                'followingSpace': True,
                'pattern': r'@[_a-zA-Z0-9а-яА-ЯёЁ]{1,}$',
                'itemTemplate': """<li data-id="{id}" class="tw:flex tw:items-center tw:gap-x-2">
                          <img src="{avatar}" class="tw:avatar tw:size-6 tw:rounded-full">
                          <span class="tw:text-black/80 tw:truncate">{username}</span>
                       </li>""",
                'outputTemplate': '<a href="{link}" data-mentioned-user-id="{id}" class="tw:mention">@{username}</a>',
            },
        ],
    },
}


THUMBNAIL_PRESERVE_FORMAT = True

INTERNAL_IPS = config('INTERNAL_IPS', cast=str.split)

# This sets the mapping of message level to message tag, which is typically rendered as a CSS class in HTML.
# https://docs.djangoproject.com/en/4.2/ref/settings/#message-tags
# Customize tags with bootstrap alert classes
MESSAGE_TAGS = {
    messages.DEBUG: 'alert-secondary',
    messages.INFO: 'alert-primary',
    messages.SUCCESS: 'alert-success',
    messages.WARNING: 'alert-warning',
    messages.ERROR: 'alert-danger',
}

YOUTUBE_API_KEY = config('YOUTUBE_API_KEY')
YOUTUBE_CHANNEL_ID = config('YOUTUBE_CHANNEL_ID', default='UCQV_rveyeAE7e2M8C-osaGQ')
YOUTUBE_FEATURED_VIDEO_IDS = config('YOUTUBE_FEATURED_VIDEO_IDS', cast=str.split, default='')

LOGS_DIR = config('LOGS_DIR', default=os.path.join(BASE_DIR, '.logs'))
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] [{levelname}] [{module}] {process:d} {thread:d} {message}',
            'style': '{',
        },
        'dev': {
            'format': '[{asctime}] [{levelname}] [{module}] {filename}:{lineno} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'dev',
        },
        'file': {
            'level': 'INFO',
            'filters': ['require_debug_false'],
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(LOGS_DIR, 'haxball_site.log'),
            'when': 'midnight',
            'interval': 1,
            'backupCount': 30,
            'formatter': 'verbose',
        },
        'mail_admins': {
            'level': 'FATAL',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['mail_admins', 'console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['mail_admins', 'console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'haxball_site': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}

UNFOLD = {
    'SITE_TITLE': 'CIS-HAXBALL',
    'SITE_HEADER': 'CIS-HAXBALL',
    'SITE_SUBHEADER': 'Административная панель',
    'SITE_ICON': lambda request: static('img/logo_try.png'),
    'SITE_FAVICONS': [
        {
            'rel': 'icon',
            'sizes': '32x32',
            'type': 'image/png',
            'href': lambda request: static('img/logo_mini.png'),
        },
    ],
    'SHOW_HISTORY': True,
    'SHOW_VIEW_ON_SITE': True,
    'SHOW_BACK_BUTTON': True,
    'SIDEBAR': {
        'show_search': False,
        'show_all_applications': False,
        'navigation': [
            {
                'title': 'Core',
                'items': [
                    {
                        'title': 'Социалочка',
                        'icon': 'handshake',
                        'link': reverse_lazy('admin:app_list', args=('core',)),
                    },
                    {
                        'title': 'Опросы',
                        'icon': 'poll',
                        'link': reverse_lazy('admin:polls_question_changelist'),
                    },
                    {
                        'title': 'Чемпионат',
                        'icon': 'trophy',
                        'link': reverse_lazy('admin:app_list', args=('tournament',)),
                    },
                    {
                        'title': 'Бронь хоста',
                        'icon': 'event',
                        'link': reverse_lazy('admin:app_list', args=('reservation',)),
                    },
                    {
                        'title': 'Уведомления',
                        'icon': 'notifications',
                        'link': reverse_lazy('admin:notifications_notification_changelist'),
                    },
                ],
            },
            {
                'title': 'Пользователи и группы',
                'icon': 'people',
                'items': [
                    {
                        'title': 'Пользователи',
                        'icon': 'person',
                        'link': reverse_lazy('admin:auth_user_changelist'),
                    },
                    {
                        'title': 'Группы',
                        'icon': 'group',
                        'link': reverse_lazy('admin:auth_group_changelist'),
                    },
                ],
            },
        ],
    },
    'COLORS': {
        'primary': {
            '50': '238, 242, 255',
            '100': '224, 231, 255',
            '200': '199, 210, 254',
            '300': '165, 180, 252',
            '400': '129, 140, 248',
            '500': '100, 120, 255',  # used for most cases in dark theme
            '600': '79, 70, 229',  # used for most cases in light theme
            '700': '67, 56, 202',
            '800': '55, 48, 163',
            '900': '49, 46, 129',
            '950': '30, 27, 75',
        },
    },
}

# OAuth2 Settings for Django OAuth Toolkit
OAUTH2_PROVIDER = {
    'OAUTH2_VALIDATOR_CLASS': 'oauth.validator.CustomOIDCValidator',
    'OIDC_ENABLED': True,
    'SCOPES': {
        'openid': 'OpenID Connect scope',
        'profile': 'Access to user profile info',
    },
    'ACCESS_TOKEN_EXPIRE_SECONDS': 3600,
    'REFRESH_TOKEN_EXPIRE_SECONDS': 3600 * 24 * 7,  # 1 week
    'AUTHORIZATION_CODE_EXPIRE_SECONDS': 600,
    'ROTATE_REFRESH_TOKEN': True,
    'PKCE_REQUIRED': False,
}
