import base64
from datetime import date

from django.test import SimpleTestCase

from kakeibo.mail_import import (
    ParsedItem,
    compute_dedup_hash,
    extract_plain_text,
    header_value,
    identify_service,
    parse_mail_body,
)

RAKUTEN_PAY_APP_BODY = """いつも楽天ペイをご利用いただきありがとうございます。
以下の内容でご利用がございました。

■利用日時：2026/08/10 12:34
■利用店舗：セブン-イレブン新宿三丁目店
■利用金額：1,000円
"""

RAKUTEN_PAY_ONLINE_BODY = """楽天ペイ（オンライン決済）をご利用いただきありがとうございます。

■注文日：2026/08/10
■加盟店名：〇〇ショップ
■お支払い金額：2,500円
"""

RAKUTEN_CARD_BODY = """楽天カードのご利用がありました。

利用日:2026/08/01
利用先:セブン-イレブン●●店
利用金額:1,000円

利用日:2026/08/02
利用先:イオン●●店
利用金額:2,000円
"""


class IdentifyServiceTests(SimpleTestCase):
    def test_identifies_rakuten_pay_app(self):
        rule = identify_service(
            "no-reply@pay.rakuten.co.jp", "【楽天ペイアプリご利用内容のお知らせ】"
        )
        self.assertEqual(rule.service, "楽天ペイ（アプリ決済）")
        self.assertEqual(rule.payment_method_name, "楽天ペイ")

    def test_identifies_rakuten_card(self):
        rule = identify_service(
            "info@mail.rakuten-card.co.jp", "【楽天カード】カード利用のお知らせ"
        )
        self.assertEqual(rule.service, "楽天カード")

    def test_unknown_sender_returns_none(self):
        self.assertIsNone(identify_service("unknown@example.com", "件名"))


class ParseMailBodyTests(SimpleTestCase):
    def test_parses_single_item_app_payment(self):
        items = parse_mail_body(RAKUTEN_PAY_APP_BODY)
        self.assertEqual(
            items,
            [ParsedItem(date(2026, 8, 10), 1000, "セブン-イレブン新宿三丁目店")],
        )

    def test_parses_single_item_online_payment(self):
        items = parse_mail_body(RAKUTEN_PAY_ONLINE_BODY)
        self.assertEqual(items, [ParsedItem(date(2026, 8, 10), 2500, "〇〇ショップ")])

    def test_parses_multiple_items_card(self):
        items = parse_mail_body(RAKUTEN_CARD_BODY)
        self.assertEqual(
            items,
            [
                ParsedItem(date(2026, 8, 1), 1000, "セブン-イレブン●●店"),
                ParsedItem(date(2026, 8, 2), 2000, "イオン●●店"),
            ],
        )

    def test_unparseable_body_returns_empty_list(self):
        self.assertEqual(parse_mail_body("形式が異なる本文です"), [])


class ExtractPlainTextTests(SimpleTestCase):
    def test_extracts_top_level_text_plain(self):
        encoded = base64.urlsafe_b64encode("本文".encode()).decode()
        payload = {"mimeType": "text/plain", "body": {"data": encoded}}
        self.assertEqual(extract_plain_text(payload), "本文")

    def test_extracts_nested_multipart_text_plain(self):
        encoded = base64.urlsafe_b64encode("ネスト本文".encode()).decode()
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/html", "body": {"data": ""}},
                {"mimeType": "text/plain", "body": {"data": encoded}},
            ],
        }
        self.assertEqual(extract_plain_text(payload), "ネスト本文")


class HeaderValueTests(SimpleTestCase):
    def test_finds_header_case_insensitively(self):
        payload = {"headers": [{"name": "Subject", "value": "件名テスト"}]}
        self.assertEqual(header_value(payload, "subject"), "件名テスト")

    def test_missing_header_returns_empty_string(self):
        self.assertEqual(header_value({"headers": []}, "Subject"), "")


class ComputeDedupHashTests(SimpleTestCase):
    def test_same_input_produces_same_hash(self):
        first = compute_dedup_hash(date(2026, 8, 1), 1000, "店舗", "楽天ペイ")
        second = compute_dedup_hash(date(2026, 8, 1), 1000, "店舗", "楽天ペイ")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_different_amount_produces_different_hash(self):
        first = compute_dedup_hash(date(2026, 8, 1), 1000, "店舗", "楽天ペイ")
        second = compute_dedup_hash(date(2026, 8, 1), 2000, "店舗", "楽天ペイ")
        self.assertNotEqual(first, second)
