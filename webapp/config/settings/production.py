from .base import *
from .base import env

DEBUG = False

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_SOCKET_PATH', default='/var/run/mysqld/mysqld.sock'),
        'OPTIONS': {'charset': 'utf8mb4'},
    }
}
