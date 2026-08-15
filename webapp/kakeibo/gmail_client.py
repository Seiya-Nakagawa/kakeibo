"""Gmail APIクライアント構築（基本設計書6.1節）。

ログイン認証（allauth、AUTHENTICATION_BACKENDS）とは別のOAuthクライアント
（GMAIL_API_*環境変数）を使用する。
"""

from django.conf import settings
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TOKEN_URI = "https://oauth2.googleapis.com/token"

SCOPE_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_LABELS = "https://www.googleapis.com/auth/gmail.labels"
SCOPE_SEND = "https://www.googleapis.com/auth/gmail.send"


def build_gmail_service(scopes: list[str]):
    credentials = Credentials(
        token=None,
        refresh_token=settings.GMAIL_API_REFRESH_TOKEN,
        client_id=settings.GMAIL_API_CLIENT_ID,
        client_secret=settings.GMAIL_API_CLIENT_SECRET,
        token_uri=TOKEN_URI,
        scopes=scopes,
    )
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)
