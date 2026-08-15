"""月次集計ロジック（基本設計書3.3節）。"""

from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Q, Sum

from kakeibo.models import (
    Account,
    BalanceRecord,
    Category,
    FixedCost,
    FixedIncome,
    Transaction,
)


def month_start(target: date) -> date:
    return target.replace(day=1)


def add_months(target: date, delta: int) -> date:
    month_index = target.month - 1 + delta
    year = target.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def month_end(target: date) -> date:
    return add_months(month_start(target), 1) - timedelta(days=1)


def _covers_month(start: date) -> Q:
    """固定費・固定収入の適用期間（start_month〜end_month）が対象月を含むかの条件。"""
    return Q(end_month__isnull=True) | Q(end_month__gte=start)


def _sum(queryset, field="amount") -> int:
    return queryset.aggregate(total=Sum(field))["total"] or 0


def variable_expense_total(target_month: date) -> int:
    """変動費実績（基本設計書3.3節）。"""
    start, end = month_start(target_month), month_end(target_month)
    return _sum(
        Transaction.objects.filter(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date__range=(start, end),
            is_deleted=False,
            is_excluded_from_aggregation=False,
        )
    )


def fixed_expense_total(target_month: date) -> int:
    """固定費実績（適用期間に対象月を含む固定費の合計）。"""
    start = month_start(target_month)
    queryset = FixedCost.objects.filter(start_month__lte=start).filter(
        _covers_month(start)
    )
    return _sum(queryset)


def income_total(target_month: date) -> int:
    """収入実績（基本設計書3.3節）。"""
    start, end = month_start(target_month), month_end(target_month)
    variable = _sum(
        Transaction.objects.filter(
            transaction_type=Transaction.TransactionType.INCOME,
            transaction_date__range=(start, end),
            is_deleted=False,
            is_excluded_from_aggregation=False,
        )
    )
    fixed = _sum(
        FixedIncome.objects.filter(start_month__lte=start).filter(_covers_month(start))
    )
    return variable + fixed


@dataclass(frozen=True)
class CategorySummary:
    category: Category
    actual: int
    budget: int | None
    diff: int | None


def category_breakdown(target_month: date) -> list[CategorySummary]:
    """カテゴリ別支出実績・予算・差額（基本設計書3.3節、5.3.1節）。

    is_aggregated=FALSEのカテゴリは集計・予算対比の対象外とする。
    """
    start, end = month_start(target_month), month_end(target_month)
    summaries = []
    categories = Category.objects.filter(
        category_type=Category.CategoryType.EXPENSE, is_aggregated=True
    ).order_by("display_order")
    for category in categories:
        variable = _sum(
            Transaction.objects.filter(
                category=category,
                transaction_date__range=(start, end),
                is_deleted=False,
                is_excluded_from_aggregation=False,
            )
        )
        fixed = _sum(
            FixedCost.objects.filter(category=category, start_month__lte=start).filter(
                _covers_month(start)
            )
        )
        actual = variable + fixed
        budget = category.monthly_budget
        diff = (budget - actual) if budget is not None else None
        summaries.append(
            CategorySummary(category=category, actual=actual, budget=budget, diff=diff)
        )
    return summaries


def total_assets_as_of(as_of: date) -> int:
    """総資産（口座ごとのbalance_recordsの最新記録を合算、基本設計書3.3節）。"""
    total = 0
    for account in Account.objects.all():
        latest = (
            BalanceRecord.objects.filter(account=account, recorded_date__lte=as_of)
            .order_by("-recorded_date")
            .first()
        )
        if latest:
            total += latest.balance
    return total


@dataclass(frozen=True)
class MonthlyBalance:
    month: date
    income: int
    expense: int
    diff: int


def monthly_balance_trend(target_month: date, months: int = 12) -> list[MonthlyBalance]:
    """月次収支推移（直近N ヶ月、基本設計書5.3.1節）。"""
    results = []
    for offset in range(months - 1, -1, -1):
        month = add_months(month_start(target_month), -offset)
        expense = variable_expense_total(month) + fixed_expense_total(month)
        income = income_total(month)
        results.append(
            MonthlyBalance(
                month=month, income=income, expense=expense, diff=income - expense
            )
        )
    return results


def asset_trend(target_month: date, months: int = 12) -> list[tuple]:
    """総資産推移（直近Nヶ月の月末時点、基本設計書5.3.1節・5.3.5節）。"""
    results = []
    for offset in range(months - 1, -1, -1):
        month = add_months(month_start(target_month), -offset)
        results.append((month, total_assets_as_of(month_end(month))))
    return results


def unclassified_transaction_count() -> int:
    return Transaction.objects.filter(
        category__isnull=True,
        transaction_type=Transaction.TransactionType.EXPENSE,
        is_deleted=False,
    ).count()
