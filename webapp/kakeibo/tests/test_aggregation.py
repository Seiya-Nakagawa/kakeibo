from datetime import date

from django.test import TestCase

from kakeibo import aggregation
from kakeibo.models import (
    Account,
    BalanceRecord,
    Category,
    FixedCost,
    FixedIncome,
    PaymentMethod,
    Transaction,
    User,
)


class MonthHelperTests(TestCase):
    def test_month_end_handles_december(self):
        self.assertEqual(aggregation.month_end(date(2026, 12, 15)), date(2026, 12, 31))

    def test_add_months_crosses_year_boundary(self):
        self.assertEqual(aggregation.add_months(date(2026, 12, 1), 2), date(2027, 2, 1))

    def test_add_months_negative(self):
        self.assertEqual(
            aggregation.add_months(date(2026, 1, 1), -1), date(2025, 12, 1)
        )


class AggregationTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="user@example.com", display_name="利用者", role=User.Role.GENERAL
        )
        self.food_category = Category.objects.create(
            name="食費",
            category_type=Category.CategoryType.EXPENSE,
            monthly_budget=30000,
            display_order=1,
        )
        self.hidden_category = Category.objects.create(
            name="振替",
            category_type=Category.CategoryType.EXPENSE,
            is_aggregated=False,
            display_order=2,
        )
        self.income_category = Category.objects.create(
            name="給与", category_type=Category.CategoryType.INCOME
        )
        self.payment_method = PaymentMethod.objects.create(name="現金")
        self.account = Account.objects.create(
            name="普通預金", account_type=Account.AccountType.BANK
        )


class VariableExpenseTotalTests(AggregationTestBase):
    def test_excludes_deleted_and_excluded_transactions(self):
        Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date=date(2026, 8, 5),
            amount=1000,
            counterpart="店A",
            category=self.food_category,
            payment_method=self.payment_method,
            source=Transaction.Source.MANUAL,
            created_by=self.user,
        )
        Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date=date(2026, 8, 6),
            amount=2000,
            counterpart="店B",
            category=self.food_category,
            payment_method=self.payment_method,
            source=Transaction.Source.MANUAL,
            created_by=self.user,
            is_deleted=True,
        )
        Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date=date(2026, 8, 7),
            amount=3000,
            counterpart="店C",
            category=self.food_category,
            payment_method=self.payment_method,
            source=Transaction.Source.MANUAL,
            created_by=self.user,
            is_excluded_from_aggregation=True,
        )
        self.assertEqual(aggregation.variable_expense_total(date(2026, 8, 1)), 1000)


class FixedExpenseTotalTests(AggregationTestBase):
    def test_includes_ongoing_fixed_cost(self):
        FixedCost.objects.create(
            payee="家賃",
            amount=50000,
            category=self.food_category,
            payment_method=self.payment_method,
            start_month=date(2026, 1, 1),
            end_month=None,
        )
        self.assertEqual(aggregation.fixed_expense_total(date(2026, 8, 1)), 50000)

    def test_excludes_fixed_cost_outside_period(self):
        FixedCost.objects.create(
            payee="旧契約",
            amount=10000,
            category=self.food_category,
            payment_method=self.payment_method,
            start_month=date(2026, 1, 1),
            end_month=date(2026, 6, 1),
        )
        self.assertEqual(aggregation.fixed_expense_total(date(2026, 8, 1)), 0)


class CategoryBreakdownTests(AggregationTestBase):
    def test_excludes_non_aggregated_categories(self):
        Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date=date(2026, 8, 5),
            amount=5000,
            counterpart="振替先",
            category=self.hidden_category,
            payment_method=self.payment_method,
            source=Transaction.Source.MANUAL,
            created_by=self.user,
        )
        summaries = aggregation.category_breakdown(date(2026, 8, 1))
        categories = [s.category for s in summaries]
        self.assertNotIn(self.hidden_category, categories)

    def test_computes_diff_against_budget(self):
        Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date=date(2026, 8, 5),
            amount=10000,
            counterpart="店",
            category=self.food_category,
            payment_method=self.payment_method,
            source=Transaction.Source.MANUAL,
            created_by=self.user,
        )
        summaries = aggregation.category_breakdown(date(2026, 8, 1))
        food_summary = next(s for s in summaries if s.category == self.food_category)
        self.assertEqual(food_summary.actual, 10000)
        self.assertEqual(food_summary.diff, 20000)


class IncomeTotalTests(AggregationTestBase):
    def test_combines_variable_and_fixed_income(self):
        Transaction.objects.create(
            transaction_type=Transaction.TransactionType.INCOME,
            transaction_date=date(2026, 8, 10),
            amount=5000,
            counterpart="臨時収入",
            category=self.income_category,
            account=self.account,
            source=Transaction.Source.MANUAL,
            created_by=self.user,
        )
        FixedIncome.objects.create(
            source="勤務先",
            amount=300000,
            category=self.income_category,
            account=self.account,
            start_month=date(2026, 1, 1),
        )
        self.assertEqual(aggregation.income_total(date(2026, 8, 1)), 305000)


class TotalAssetsTests(AggregationTestBase):
    def test_uses_latest_record_on_or_before_date(self):
        BalanceRecord.objects.create(
            account=self.account, recorded_date=date(2026, 7, 1), balance=100000
        )
        BalanceRecord.objects.create(
            account=self.account, recorded_date=date(2026, 8, 1), balance=150000
        )
        self.assertEqual(aggregation.total_assets_as_of(date(2026, 8, 15)), 150000)
        self.assertEqual(aggregation.total_assets_as_of(date(2026, 7, 15)), 100000)


class UnclassifiedCountTests(AggregationTestBase):
    def test_counts_only_unclassified_expense(self):
        Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date=date(2026, 8, 1),
            amount=1000,
            counterpart="未分類店",
            payment_method=self.payment_method,
            source=Transaction.Source.MANUAL,
            created_by=self.user,
        )
        self.assertEqual(aggregation.unclassified_transaction_count(), 1)
