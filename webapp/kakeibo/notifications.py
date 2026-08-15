"""エラー通知メール送信（要件6.5.1、基本設計書7.4節）。"""

import base64
import logging
from email.mime.text import MIMEText

from django.conf import settings

from kakeibo.gmail_client import SCOPE_SEND, build_gmail_service

logger = logging.getLogger(__name__)


def notify_admin(subject: str, body: str) -> bool:
    """管理者へエラー通知メールを送信する（メール取込の解析失敗、バッチの異常終了、バックアップの失敗）。

    通知自体の失敗でバッチ処理全体を止めないよう、例外は送出せずログ出力のみ行う
    （呼び出し元は戻り値のTrue/Falseで送信可否を判定できる）。
    """
    if not settings.NOTIFICATION_RECIPIENT_EMAIL:
        logger.warning(
            "NOTIFICATION_RECIPIENT_EMAIL未設定のため通知メールを送信しません: %s",
            subject,
        )
        return False

    message = MIMEText(body)
    message["to"] = settings.NOTIFICATION_RECIPIENT_EMAIL
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    try:
        service = build_gmail_service([SCOPE_SEND])
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
    except Exception:
        logger.exception("通知メールの送信に失敗しました: subject=%s", subject)
        return False
    return True
