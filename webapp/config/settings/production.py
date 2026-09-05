from .base import *
from .base import env

DEBUG = False

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# TLSはingress-nginxで終端されPodへはプレーンHTTPで転送されるため、明示しないと
# request.is_secure()がFalseになりOAuthのredirect_uriがhttp://で生成され
# （Google Cloud Console側はhttps://で登録）redirect_uri_mismatchになる。
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# 基本設計書1.1.1節: /kakeibo配下で動作させるため、URL逆引き・リダイレクト先に
# プレフィックスを付与する。Ingress側は/kakeiboを除去してバックエンドへ転送する
# （k8s/ingress.yamlのrewrite-target）ため、Django側は付与のみを担う。
FORCE_SCRIPT_NAME = env("FORCE_SCRIPT_NAME", default="/kakeibo")

# STATIC_URLをFORCE_SCRIPT_NAME起点の絶対パスにする。base.pyの相対パス（"static/"）の
# ままだと、ページの階層が深いURL（例: /kakeibo/admin/login/）で相対解決の基準が
# ずれてCSS/画像が404になる。WhiteNoiseMiddleware側はFORCE_SCRIPT_NAMEのプレフィックスを
# 自動的に除去して実際のリクエストパスと突き合わせるため、ここでの絶対パス化と整合する。
STATIC_URL = f"{FORCE_SCRIPT_NAME}/static/"

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
