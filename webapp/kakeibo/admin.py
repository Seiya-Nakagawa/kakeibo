from django import forms
from django.contrib import admin

from kakeibo.models import (
    Account,
    BalanceRecord,
    Category,
    EmailImportLog,
    FixedCost,
    FixedIncome,
    PaymentMethod,
    StoreRule,
    Transaction,
    User,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category_type",
        "monthly_budget",
        "is_aggregated",
        "display_order",
    )
    list_filter = ("category_type", "is_aggregated")
    search_fields = ("name",)
    ordering = ("category_type", "display_order")


@admin.register(StoreRule)
class StoreRuleAdmin(admin.ModelAdmin):
    list_display = ("keyword", "category", "priority", "is_auto_generated")
    list_filter = ("is_auto_generated", "category")
    search_fields = ("keyword",)
    ordering = ("priority",)


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "display_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("display_order",)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "account_type", "currency", "display_order", "is_active")
    list_filter = ("account_type", "is_active")
    search_fields = ("name",)
    ordering = ("display_order",)


@admin.register(BalanceRecord)
class BalanceRecordAdmin(admin.ModelAdmin):
    """要件4.8では明示されていないが、残高記録の不正値を管理者が是正できるようAdminにも登録する。"""

    list_display = ("account", "recorded_date", "balance")
    list_filter = ("account",)
    ordering = ("-recorded_date",)


@admin.register(FixedCost)
class FixedCostAdmin(admin.ModelAdmin):
    list_display = (
        "payee",
        "amount",
        "category",
        "payment_method",
        "start_month",
        "end_month",
    )
    list_filter = ("category",)
    search_fields = ("payee",)
    ordering = ("payee", "start_month")


@admin.register(FixedIncome)
class FixedIncomeAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "amount",
        "category",
        "account",
        "start_month",
        "end_month",
    )
    list_filter = ("category",)
    search_fields = ("source",)
    ordering = ("source", "start_month")


@admin.register(EmailImportLog)
class EmailImportLogAdmin(admin.ModelAdmin):
    """要件4.8では明示されていないが、取込ログの調査に必要なため参照専用でAdminに登録する。"""

    list_display = ("gmail_message_id", "service", "status", "executed_at")
    list_filter = ("status", "service")
    search_fields = ("gmail_message_id",)
    ordering = ("-executed_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class UserAdminForm(forms.ModelForm):
    """passwordはGoogle OAuth専用ログインのため未使用（set_unusable_password）とし、フォームに出さない。"""

    class Meta:
        model = User
        fields = ("email", "display_name", "role", "is_active")


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    form = UserAdminForm
    list_display = ("email", "display_name", "role", "is_active", "last_login")
    list_filter = ("role", "is_active")
    search_fields = ("email", "display_name")
    readonly_fields = ("google_sub", "last_login", "created_at", "updated_at")
    ordering = ("email",)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.set_unusable_password()
        super().save_model(request, obj, form, change)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """要件4.8では明示されていないが、メール取込データの不正値を管理者が是正できるようAdminにも登録する。"""

    list_display = (
        "transaction_date",
        "transaction_type",
        "counterpart",
        "amount",
        "category",
        "source",
        "is_deleted",
    )
    list_filter = ("transaction_type", "source", "category", "is_deleted")
    search_fields = ("counterpart", "memo")
    ordering = ("-transaction_date",)
