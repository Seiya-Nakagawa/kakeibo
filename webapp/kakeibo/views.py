import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from kakeibo.categorization import register_learned_rule
from kakeibo.forms import CategoryAssignForm, TransactionFilterForm, TransactionForm
from kakeibo.models import Transaction


class HomeView(TemplateView):
    """ログイン後の暫定的な遷移先（画面2 ダッシュボードは別Issueで実装）。"""

    template_name = "kakeibo/home.html"


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
