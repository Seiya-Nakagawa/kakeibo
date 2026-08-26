import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import (
    CreateView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from kakeibo import aggregation
from kakeibo.categorization import register_learned_rule
from kakeibo.forms import (
    BalanceRecordForm,
    CategoryAssignForm,
    TransactionFilterForm,
    TransactionForm,
)
from kakeibo.models import BalanceRecord, Transaction


def _parse_target_month(raw: str | None) -> date:
    if raw:
        try:
            year, month = raw.split("-")
            return date(int(year), int(month), 1)
        except ValueError:
            pass
    return aggregation.month_start(timezone.localdate())


class DashboardView(TemplateView):
    """画面2 ダッシュボード（基本設計書5.3.1節）。"""

    template_name = "kakeibo/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        target_month = _parse_target_month(self.request.GET.get("month"))

        category_summaries = aggregation.category_breakdown(target_month)
        expense_total = aggregation.variable_expense_total(
            target_month
        ) + aggregation.fixed_expense_total(target_month)
        income = aggregation.income_total(target_month)
        balance_trend = aggregation.monthly_balance_trend(target_month)
        assets = aggregation.asset_trend(target_month)

        context.update(
            {
                "target_month": target_month,
                "income_total": income,
                "expense_total": expense_total,
                "balance_diff": income - expense_total,
                "category_summaries": category_summaries,
                "unclassified_count": aggregation.unclassified_transaction_count(),
                "expense_trend_labels": [
                    m.month.strftime("%Y-%m") for m in balance_trend
                ],
                "expense_trend_data": [m.expense for m in balance_trend],
                "category_composition_labels": [
                    s.category.name for s in category_summaries if s.actual > 0
                ],
                "category_composition_data": [
                    s.actual for s in category_summaries if s.actual > 0
                ],
                "balance_trend_labels": [
                    m.month.strftime("%Y-%m") for m in balance_trend
                ],
                "balance_trend_income": [m.income for m in balance_trend],
                "balance_trend_expense": [m.expense for m in balance_trend],
                "balance_trend_diff": [m.diff for m in balance_trend],
                "asset_trend_labels": [m.strftime("%Y-%m") for m, _ in assets],
                "asset_trend_data": [total for _, total in assets],
            }
        )
        return context


@method_decorator(login_not_required, name="dispatch")
class AccessDeniedView(TemplateView):
    """画面8: 未登録のGoogleアカウントでログインした際に表示する。"""

    template_name = "kakeibo/access_denied.html"


def _filtered_transactions(request):
    """画面3 取引一覧・CSV出力で共通の絞り込み条件（基本設計書5.3.2節）。"""
    queryset = (
        Transaction.objects.filter(is_deleted=False)
        .select_related("category", "payment_method", "account", "created_by")
        .order_by("-transaction_date", "-id")
    )
    form = TransactionFilterForm(request.GET or None)
    if form.is_valid():
        data = form.cleaned_data
        if data.get("date_from"):
            queryset = queryset.filter(transaction_date__gte=data["date_from"])
        if data.get("date_to"):
            queryset = queryset.filter(transaction_date__lte=data["date_to"])
        if data.get("category"):
            queryset = queryset.filter(category=data["category"])
        if data.get("payment_method"):
            queryset = queryset.filter(payment_method=data["payment_method"])
        if data.get("amount_min") is not None:
            queryset = queryset.filter(amount__gte=data["amount_min"])
        if data.get("amount_max") is not None:
            queryset = queryset.filter(amount__lte=data["amount_max"])
        if data.get("counterpart"):
            queryset = queryset.filter(counterpart__icontains=data["counterpart"])
    return queryset, form


class TransactionListView(ListView):
    """画面3 取引一覧（基本設計書5.3.2節）。"""

    template_name = "kakeibo/transaction_list.html"
    context_object_name = "transactions"
    paginate_by = 50

    def get_queryset(self):
        queryset, self.filter_form = _filtered_transactions(self.request)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        return context


class TransactionExportCsvView(View):
    """画面3 CSV出力（要件4.7.6）。"""

    def get(self, request, *args, **kwargs):
        queryset, _ = _filtered_transactions(request)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="transactions.csv"'
        response.write("﻿")  # Excelでの文字化けを防ぐBOM
        writer = csv.writer(response)
        writer.writerow(
            [
                "日付",
                "種別",
                "店舗名・収入元",
                "カテゴリ",
                "金額",
                "決済手段/入金先口座",
                "登録者",
            ]
        )
        for transaction in queryset:
            writer.writerow(
                [
                    transaction.transaction_date,
                    transaction.get_transaction_type_display(),
                    transaction.counterpart,
                    transaction.category.name if transaction.category else "未分類",
                    transaction.amount,
                    transaction.payment_method or transaction.account or "",
                    transaction.created_by.display_name,
                ]
            )
        return response


class TransactionCreateView(CreateView):
    """画面4 取引登録（基本設計書5.3.3節）。"""

    model = Transaction
    form_class = TransactionForm
    template_name = "kakeibo/transaction_form.html"
    success_url = reverse_lazy("transaction-list")

    def form_valid(self, form):
        form.instance.source = Transaction.Source.MANUAL
        form.instance.created_by = self.request.user
        messages.success(self.request, "取引を登録しました。")
        return super().form_valid(form)


class TransactionUpdateView(UpdateView):
    """画面4 取引編集（基本設計書5.3.3節）。"""

    model = Transaction
    form_class = TransactionForm
    template_name = "kakeibo/transaction_form.html"
    success_url = reverse_lazy("transaction-list")

    def get_queryset(self):
        return Transaction.objects.filter(is_deleted=False)

    def form_valid(self, form):
        messages.success(self.request, "取引を更新しました。")
        return super().form_valid(form)


class TransactionDeleteView(View):
    """画面3 取引の削除（要件2.1: 論理削除、物理削除しない）。"""

    def post(self, request, pk, *args, **kwargs):
        transaction = get_object_or_404(Transaction, pk=pk, is_deleted=False)
        transaction.is_deleted = True
        transaction.save(update_fields=["is_deleted", "updated_at"])
        messages.success(request, "取引を削除しました。")
        return redirect("transaction-list")


class UnclassifiedTransactionListView(ListView):
    """画面5 未分類取引一覧（基本設計書5.3.4節）。"""

    template_name = "kakeibo/unclassified_transaction_list.html"
    context_object_name = "transactions"

    def get_queryset(self):
        return (
            Transaction.objects.filter(
                is_deleted=False,
                category__isnull=True,
                transaction_type=Transaction.TransactionType.EXPENSE,
            )
            .select_related("payment_method")
            .order_by("-transaction_date", "-id")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["assign_form"] = CategoryAssignForm()
        return context


class AssignCategoryView(View):
    """画面5 カテゴリ割当（要件4.2.5〜4.2.6: 割当時に店舗ルールへ自動学習登録する）。"""

    def post(self, request, pk, *args, **kwargs):
        transaction = get_object_or_404(
            Transaction, pk=pk, is_deleted=False, category__isnull=True
        )
        form = CategoryAssignForm(request.POST)
        if form.is_valid():
            category = form.cleaned_data["category"]
            transaction.category = category
            transaction.save(update_fields=["category", "updated_at"])
            register_learned_rule(category, transaction.counterpart)
            messages.success(request, "カテゴリを割り当てました。")
        else:
            messages.error(request, "カテゴリの割当に失敗しました。")
        return redirect("unclassified-transaction-list")


def _account_balance_context(balance_form=None) -> dict:
    """画面6 資産残高で共通の集計データ（基本設計書5.3.5節）。"""
    today = timezone.localdate()
    assets = aggregation.asset_trend(aggregation.month_start(today))
    return {
        "as_of": today,
        "total_assets": aggregation.total_assets_as_of(today),
        "assets_by_type": aggregation.assets_by_account_type(today),
        "account_balances": aggregation.account_balances(today),
        "asset_trend_labels": [m.strftime("%Y-%m") for m, _ in assets],
        "asset_trend_data": [total for _, total in assets],
        "balance_form": balance_form or BalanceRecordForm(),
    }


class AccountBalanceView(TemplateView):
    """画面6 資産残高（基本設計書5.3.5節）。"""

    template_name = "kakeibo/account_balance.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_account_balance_context())
        return context


class BalanceRecordCreateView(FormView):
    """画面7 残高記録入力（要件4.6.2〜4.6.3: 同一口座・同一基準日は上書き）。"""

    form_class = BalanceRecordForm
    template_name = "kakeibo/account_balance.html"
    success_url = reverse_lazy("account-balance")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method == "POST":
            existing = BalanceRecord.objects.filter(
                account_id=self.request.POST.get("account"),
                recorded_date=self.request.POST.get("recorded_date") or None,
            ).first()
            if existing:
                kwargs["instance"] = existing
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "残高を記録しました。")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "残高の記録に失敗しました。")
        context = _account_balance_context(balance_form=form)
        return self.render_to_response(context)
