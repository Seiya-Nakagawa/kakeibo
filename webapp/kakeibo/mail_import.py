"""決済通知メールの解析（基本設計書3.1節）。

注意: 各サービスの本文解析用正規表現は、Rakuten系サービスで一般的に知られている
通知メールの書式（日付・利用先・金額のラベル付き記載）を基にした暫定実装であり、
実際に届く最新の通知メール本文で検証できていない。運用開始前に実メールのサンプルで
必ず動作確認し、必要に応じてラベルのパターンを調整すること。
"""

import base64
import hashlib
import re
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ServiceRule:
    """サービス識別ルール（基本設計書3.1.1節）。"""

    service: str
    sender: str
    subject_contains: str
    payment_method_name: str


# 対応サービスの追加は、この一覧への行追加のみで完結する（要件4.1.2.9）。
SERVICE_RULES = [
    ServiceRule(
        service="楽天ペイ（アプリ決済）",
        sender="no-reply@pay.rakuten.co.jp",
        subject_contains="楽天ペイアプリご利用内容",
        payment_method_name="楽天ペイ",
    ),
    ServiceRule(
        service="楽天ペイ（オンライン決済）",
        sender="payment@checkout.rakuten.co.jp",
        subject_contains="楽天ペイ（オンライン決済）",
        payment_method_name="楽天ペイ(オンライン)",
    ),
    ServiceRule(
        service="楽天ペイ（注文受付）",
        sender="order@checkout.rakuten.co.jp",
        subject_contains="楽天ペイ 注文受付",
        payment_method_name="楽天ペイ(オンライン)",
    ),
    ServiceRule(
        service="楽天カード",
        sender="info@mail.rakuten-card.co.jp",
        subject_contains="カード利用のお知らせ",
        payment_method_name="楽天カード",
    ),
]


def identify_service(sender: str, subject: str) -> ServiceRule | None:
    """送信元アドレスと件名からサービスを識別する（基本設計書3.1.1節）。"""
    for rule in SERVICE_RULES:
        if rule.sender in sender and rule.subject_contains in subject:
            return rule
    return None


@dataclass(frozen=True)
class ParsedItem:
    transaction_date: date
    amount: int
    counterpart: str


_DATE_LABELS = r"(?:ご)?利用日時?|注文日"
_STORE_LABELS = r"(?:ご)?利用先|(?:ご)?利用店舗|加盟店名"
_AMOUNT_LABELS = r"(?:ご)?利用金額|お支払い?金額"

_ITEM_PATTERN = re.compile(
    rf"(?:{_DATE_LABELS})[:：]\s*(?P<date>\d{{4}}[/年]\d{{1,2}}[/月]\d{{1,2}})日?"
    rf"(?:\s*\d{{1,2}}[:：]\d{{2}})?"
    rf".*?(?:{_STORE_LABELS})[:：]\s*(?P<store>[^\r\n]+?)\s*[\r\n]"
    rf".*?(?:{_AMOUNT_LABELS})[:：]\s*(?P<amount>[\d,]+)円",
    re.DOTALL,
)


def parse_mail_body(body: str) -> list[ParsedItem]:
    """メール本文から取引明細を抽出する（複数明細対応、要件4.1.2.5）。

    1通に複数明細を含む場合（楽天カード等）に対応するため、本文中に現れる
    日付・利用先・金額のラベル付き記載を順に走査してすべて抽出する。
    """
    items = []
    for match in _ITEM_PATTERN.finditer(body):
        year, month, day = re.split(r"[/年]", match.group("date"))
        items.append(
            ParsedItem(
                transaction_date=date(int(year), int(month), int(day)),
                amount=int(match.group("amount").replace(",", "")),
                counterpart=match.group("store").strip(),
            )
        )
    return items


def extract_plain_text(payload: dict) -> str:
    """Gmail APIのmessage.payloadからtext/plain本文を抽出する。"""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            return _decode_base64url(data)
    for part in payload.get("parts", []) or []:
        text = extract_plain_text(part)
        if text:
            return text
    return ""


def _decode_base64url(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def compute_dedup_hash(
    transaction_date: date, amount: int, counterpart: str, payment_method_name: str
) -> str:
    """取引単位の重複排除用ハッシュ（基本設計書3.1.3節）。"""
    raw = f"{transaction_date.isoformat()}|{amount}|{counterpart}|{payment_method_name}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def header_value(payload: dict, name: str) -> str:
    for header in payload.get("headers", []) or []:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""
