import csv
import os
import tempfile

from django.core.management import CommandError, call_command
from django.test import TestCase

from kakeibo.models import Category, PaymentMethod, Transaction, User


def _write_csv(test_case: TestCase, header: list[str], rows: list[list]) -> str:
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    test_case.addCleanup(os.remove, path)
    return path


class ImportLegacyDataCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="a@example.com", display_name="太郎")
        self.category = Category.objects.create(
            name="食費", category_type=Category.CategoryType.EXPENSE
        )
        self.payment_method = PaymentMethod.objects.create(name="楽天ペイ")

    def test_categories_and_store_rules_are_imported_together(self):
        categories_csv = _write_csv(
            self, ["カテゴリ名", "月次予算", "集計対象"], [["日用品", "5000", "TRUE"]]
        )
        store_rules_csv = _write_csv(
            self, ["店舗名キーワード", "カテゴリ名"], [["ドラッグストア", "日用品"]]
        )

        call_command(
            "import_legacy_data",
            categories=categories_csv,
            store_rules=store_rules_csv,
        )

        self.assertTrue(Category.objects.filter(name="日用品").exists())

    def test_transactions_without_imported_by_raises(self):
        transactions_csv = _write_csv(
            self,
            [
                "日付",
                "金額",
                "店舗名",
                "決済手段",
                "カテゴリ",
                "メモ",
                "登録方法",
                "重複排除キー",
            ],
            [
                [
                    "2026-08-10",
                    "1000",
                    "セブンイレブン",
                    "楽天ペイ",
                    "食費",
                    "",
                    "auto",
                    "h",
                ]
            ],
        )

        with self.assertRaises(CommandError):
            call_command("import_legacy_data", transactions=transactions_csv)

        self.assertEqual(Transaction.objects.count(), 0)

    def test_unknown_imported_by_email_raises(self):
        transactions_csv = _write_csv(
            self,
            [
                "日付",
                "金額",
                "店舗名",
                "決済手段",
                "カテゴリ",
                "メモ",
                "登録方法",
                "重複排除キー",
            ],
            [
                [
                    "2026-08-10",
                    "1000",
                    "セブンイレブン",
                    "楽天ペイ",
                    "食費",
                    "",
                    "auto",
                    "h",
                ]
            ],
        )

        with self.assertRaises(CommandError):
            call_command(
                "import_legacy_data",
                transactions=transactions_csv,
                imported_by="unknown@example.com",
            )

    def test_successful_transaction_import_reports_verification(self):
        transactions_csv = _write_csv(
            self,
            [
                "日付",
                "金額",
                "店舗名",
                "決済手段",
                "カテゴリ",
                "メモ",
                "登録方法",
                "重複排除キー",
            ],
            [
                [
                    "2026-08-10",
                    "1000",
                    "セブンイレブン",
                    "楽天ペイ",
                    "食費",
                    "",
                    "auto",
                    "h",
                ]
            ],
        )

        call_command(
            "import_legacy_data",
            transactions=transactions_csv,
            imported_by="a@example.com",
        )

        self.assertEqual(Transaction.objects.count(), 1)

    def test_missing_master_raises_command_error(self):
        transactions_csv = _write_csv(
            self,
            [
                "日付",
                "金額",
                "店舗名",
                "決済手段",
                "カテゴリ",
                "メモ",
                "登録方法",
                "重複排除キー",
            ],
            [
                [
                    "2026-08-10",
                    "1000",
                    "セブンイレブン",
                    "未登録決済手段",
                    "食費",
                    "",
                    "auto",
                    "h",
                ]
            ],
        )

        with self.assertRaisesMessage(CommandError, "未登録決済手段"):
            call_command(
                "import_legacy_data",
                transactions=transactions_csv,
                imported_by="a@example.com",
            )
