import datetime

from .base import *

SITE_ID = 1
DEBUG = True
TEMPLATE_DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'edtrac',
        'USER': 'mtrack',
        'PASSWORD': 'mtrack',
        'HOST': 'localhost',
    }
}

INSTALLED_APPS += (
   # 'django_extensions',
   'django.contrib.staticfiles',
   #'debug_toolbar',
)

#MIDDLEWARE_CLASSES += (
#   'debug_toolbar.middleware.DebugToolbarMiddleware',
#)

INTERNAL_IPS += ('127.0.0.1', '::1')
DEBUG_TOOLBAR_CONFIG = {
    'INTERCEPT_REDIRECTS': False
}

LOGGING['handlers']['mail_admins'] = {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
        }

LOGGING['loggers']['django.request'] = {
            'handlers': ['mail_admins'],
            'level': 'DEBUG',
            'propagate': True,
            }

SPREADSHEETS_PATH = filedir

TEMPLATE_DIRS = { '/home/fsarker/projects/rapidsms-sandbox/edtrac/edtrac-env/django/contrib/admin/templates/' }

STATICFILES_DIR  = { '/home/fsarker/projects/rapidsms-sandbox/edtrac/edtrac-env/django/contrib/admin/static/admin/' }
