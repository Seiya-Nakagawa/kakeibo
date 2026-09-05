import csv
import os
import tempfile
from datetime import date

from django.test import TestCase

from kakeibo.legacy_import import (
    LegacyImportError,
    import_categories,
    import_fixed_costs,
    import_store_rules,
    import_transactions,
    verify_transactions,
)
from kakeibo.models import (
    Category,
    FixedCost,
    PaymentMethod,
    StoreRule,
    Transaction,
    User,
)


def _write_csv(test_case: TestCase, header: list[str], rows: list[list]) -> str:
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    test_case.addCleanup(os.remove, path)
    return path


class ImportCategoriesTests(TestCase):
    def test_creates_categories_preserving_order_and_budget_zero_as_none(self):
        path = _write_csv(
            self,
            ["カテゴリ名", "月次予算", "集計対象"],
            [
                ["食費", "30000", "TRUE"],
                ["対象外", "0", "FALSE"],
            ],
        )

        result = import_categories(path)

        self.assertEqual((result.created, result.updated), (2, 0))
        food = Category.objects.get(name="食費")
        self.assertEqual(food.monthly_budget, 30000)
        self.assertTrue(food.is_aggregated)
        self.assertEqual(food.display_order, 0)

        excluded = Category.objects.get(name="対象外")
        self.assertIsNone(excluded.monthly_budget)
        self.assertFalse(excluded.is_aggregated)
        self.assertEqual(excluded.display_order, 1)

    def test_rerun_updates_instead_of_duplicating(self):
        path = _write_csv(
            self, ["カテゴリ名", "月次予算", "集計対象"], [["食費", "30000", "TRUE"]]
        )
        import_categories(path)

        path2 = _write_csv(
            self, ["カテゴリ名", "月次予算", "集計対象"], [["食費", "40000", "TRUE"]]
        )
        result = import_categories(path2)

        self.assertEqual((result.created, result.updated), (0, 1))
        self.assertEqual(Category.objects.count(), 1)
        self.assertEqual(Category.objects.get().monthly_budget, 40000)

    def test_footer_total_row_is_skipped(self):
        path = _write_csv(
            self,
            ["カテゴリ名", "月次予算", "集計対象"],
            [["食費", "30000", "TRUE"], ["合計", "30000", ""]],
        )

        import_categories(path)

        self.assertEqual(Category.objects.count(), 1)


class ImportStoreRulesTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="食費", category_type=Category.CategoryType.EXPENSE
        )

    def test_creates_rules_with_priority_from_row_order(self):
        path = _write_csv(
            self,
            ["店舗名キーワード", "カテゴリ名"],
            [["セブンイレブン", "食費"], ["ベルク", "食費"]],
        )

        result = import_store_rules(path)

        self.assertEqual((result.created, result.updated), (2, 0))
        self.assertEqual(StoreRule.objects.get(keyword="セブンイレブン").priority, 1)
        self.assertEqual(StoreRule.objects.get(keyword="ベルク").priority, 2)
        self.assertFalse(StoreRule.objects.get(keyword="ベルク").is_auto_generated)

    def test_missing_category_raises_and_rolls_back(self):
        path = _write_csv(
            self,
            ["店舗名キーワード", "カテゴリ名"],
            [["セブンイレブン", "食費"], ["謎の店", "未登録カテゴリ"]],
        )

        with self.assertRaisesMessage(LegacyImportError, "未登録カテゴリ"):
            import_store_rules(path)

        self.assertEqual(StoreRule.objects.count(), 0)


class ImportFixedCostsTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="住宅", category_type=Category.CategoryType.EXPENSE
        )
        self.payment_method = PaymentMethod.objects.create(name="口座引落")

    def test_creates_fixed_cost_with_parsed_start_month(self):
        path = _write_csv(
            self,
            ["支払先", "金額", "カテゴリ名", "決済手段", "開始月", "メモ"],
            [["住宅ローン", "80000", "住宅", "口座引落", "2026/04", "35年ローン"]],
        )

        result = import_fixed_costs(path)

        self.assertEqual((result.created, result.updated), (1, 0))
        fixed_cost = FixedCost.objects.get()
        self.assertEqual(fixed_cost.amount, 80000)
        self.assertEqual(fixed_cost.start_month.isoformat(), "2026-04-01")
        self.assertEqual(fixed_cost.memo, "35年ローン")

    def test_blank_start_month_uses_always_applied_constant(self):
        path = _write_csv(
            self,
            ["支払先", "金額", "カテゴリ名", "決済手段", "開始月", "メモ"],
            [["サブスク", "1000", "住宅", "口座引落", "", ""]],
        )

        import_fixed_costs(path)

        self.assertEqual(FixedCost.objects.get().start_month.isoformat(), "2000-01-01")

    def test_rerun_updates_by_payee_and_start_month(self):
        path = _write_csv(
            self,
            ["支払先", "金額", "カテゴリ名", "決済手段", "開始月", "メモ"],
            [["住宅ローン", "80000", "住宅", "口座引落", "2026/04", ""]],
        )
        import_fixed_costs(path)

        path2 = _write_csv(
            self,
            ["支払先", "金額", "カテゴリ名", "決済手段", "開始月", "メモ"],
            [["住宅ローン", "85000", "住宅", "口座引落", "2026/04", ""]],
        )
        result = import_fixed_costs(path2)

        self.assertEqual((result.created, result.updated), (0, 1))
        self.assertEqual(FixedCost.objects.count(), 1)
        self.assertEqual(FixedCost.objects.get().amount, 85000)

    def test_missing_payment_method_raises_and_rolls_back(self):
        path = _write_csv(
            self,
            ["支払先", "金額", "カテゴリ名", "決済手段", "開始月", "メモ"],
            [["住宅ローン", "80000", "住宅", "未登録決済手段", "2026/04", ""]],
        )

        with self.assertRaisesMessage(LegacyImportError, "未登録決済手段"):
            import_fixed_costs(path)

        self.assertEqual(FixedCost.objects.count(), 0)


class ImportTransactionsTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="食費", category_type=Category.CategoryType.EXPENSE
        )
        self.payment_method = PaymentMethod.objects.create(name="楽天ペイ")
        self.user = User.objects.create_user(email="a@example.com", display_name="太郎")

    def _csv(self, rows):
        return _write_csv(
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
            rows,
        )

    def test_creates_transactions_and_skips_fixed_rows(self):
        path = self._csv(
            [
                [
                    "2026-08-10",
                    "1000",
                    "セブンイレブン",
                    "楽天ペイ",
                    "食費",
                    "",
                    "auto",
                    "old-hash-1",
                ],
                [
                    "2026-08-11",
                    "500",
                    "ベルク",
                    "楽天ペイ",
                    "食費",
                    "",
                    "manual",
                    "old-hash-2",
                ],
                [
                    "2026-08-01",
                    "80000",
                    "住宅ローン",
                    "口座引落",
                    "食費",
                    "",
                    "fixed",
                    "old-hash-3",
                ],
            ]
        )

        result = import_transactions(path, self.user)

        self.assertEqual((result.created, result.updated), (2, 0))
        self.assertEqual(result.skipped_fixed, 1)
        self.assertEqual(Transaction.objects.count(), 2)

        manual_tx = Transaction.objects.get(counterpart="ベルク")
        self.assertEqual(manual_tx.source, Transaction.Source.MANUAL)
        self.assertEqual(manual_tx.created_by, self.user)
        self.assertEqual(
            manual_tx.transaction_type, Transaction.TransactionType.EXPENSE
        )

    def test_dedup_hash_is_recomputed_with_django_algorithm(self):
        from kakeibo.mail_import import compute_dedup_hash

        path = self._csv(
            [
                [
                    "2026-08-10",
                    "1000",
                    "セブンイレブン",
                    "楽天ペイ",
                    "食費",
                    "",
                    "auto",
                    "gas-original-hash",
                ]
            ]
        )

        import_transactions(path, self.user)

        expected_hash = compute_dedup_hash(
            date(2026, 8, 10), 1000, "セブンイレブン", "楽天ペイ"
        )
        transaction_obj = Transaction.objects.get()
        self.assertEqual(transaction_obj.dedup_hash, expected_hash)
        self.assertNotEqual(transaction_obj.dedup_hash, "gas-original-hash")

    def test_rerun_is_idempotent(self):
        path = self._csv(
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
            ]
        )

        import_transactions(path, self.user)
        result = import_transactions(path, self.user)

        self.assertEqual((result.created, result.updated), (0, 1))
        self.assertEqual(Transaction.objects.count(), 1)

    def test_missing_category_raises_and_rolls_back(self):
        path = self._csv(
            [
                [
                    "2026-08-10",
                    "1000",
                    "セブンイレブン",
                    "楽天ペイ",
                    "未登録カテゴリ",
                    "",
                    "auto",
                    "h",
                ]
            ]
        )

        with self.assertRaisesMessage(LegacyImportError, "未登録カテゴリ"):
            import_transactions(path, self.user)

        self.assertEqual(Transaction.objects.count(), 0)


class VerifyTransactionsTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="食費", category_type=Category.CategoryType.EXPENSE
        )
        self.payment_method = PaymentMethod.objects.create(name="楽天ペイ")
        self.user = User.objects.create_user(email="a@example.com", display_name="太郎")

    def _csv(self, rows):
        return _write_csv(
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
            rows,
        )

    def test_matching_monthly_totals_report_no_mismatch(self):
        path = self._csv(
            [
                [
                    "2026-08-10",
                    "1000",
                    "セブンイレブン",
                    "楽天ペイ",
                    "食費",
                    "",
                    "auto",
                    "h1",
                ],
                ["2026-08-11", "500", "ベルク", "楽天ペイ", "食費", "", "auto", "h2"],
            ]
        )
        result = import_transactions(path, self.user)

        verifications = verify_transactions(result)

        self.assertEqual(len(verifications), 1)
        self.assertTrue(verifications[0].matches)
        self.assertEqual(verifications[0].csv_count, 2)
        self.assertEqual(verifications[0].csv_total, 1500)
        self.assertEqual(verifications[0].db_total, 1500)

    def test_db_side_tampering_is_detected_as_mismatch(self):
        path = self._csv(
            [
                [
                    "2026-08-10",
                    "1000",
                    "セブンイレブン",
                    "楽天ペイ",
                    "食費",
                    "",
                    "auto",
                    "h1",
                ]
            ]
        )
        result = import_transactions(path, self.user)

        tampered = Transaction.objects.get()
        tampered.amount = 999
        tampered.save()

        verifications = verify_transactions(result)

        self.assertFalse(verifications[0].matches)
