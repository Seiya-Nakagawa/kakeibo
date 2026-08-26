from .base import *
from .base import env

DEBUG = False

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# 基本設計書1.1.1節: /kakeibo配下で動作させるため、URL逆引き・リダイレクト先に
# プレフィックスを付与する。Ingress側は/kakeiboを除去してバックエンドへ転送する
# （k8s/ingress.yamlのrewrite-target）ため、Django側は付与のみを担う。
FORCE_SCRIPT_NAME = env("FORCE_SCRIPT_NAME", default="/kakeibo")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_SOCKET_PATH", default="/var/run/mysqld/mysqld.sock"),
        "OPTIONS": {"charset": "utf8mb4"},
    }
}
