from django import forms

from kakeibo.models import BalanceRecord, Category, Transaction


class TransactionForm(forms.ModelForm):
    """画面4 取引登録・編集: 種別（支出/収入）でフォーム項目の要否が変わる（基本設計書5.3.3節）。"""

    class Meta:
        model = Transaction
        fields = (
            "transaction_type",
            "transaction_date",
            "amount",
            "counterpart",
            "category",
            "payment_method",
            "account",
            "memo",
            "is_excluded_from_aggregation",
        )
        widgets = {
            "transaction_type": forms.RadioSelect,
            "transaction_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        transaction_type = cleaned_data.get("transaction_type")
        category = cleaned_data.get("category")

        if transaction_type == Transaction.TransactionType.EXPENSE:
            if not cleaned_data.get("payment_method"):
                self.add_error("payment_method", "支出には決済手段が必須です。")
            cleaned_data["account"] = None
        elif transaction_type == Transaction.TransactionType.INCOME:
            if not cleaned_data.get("account"):
                self.add_error("account", "収入には入金先口座が必須です。")
            if not category:
                self.add_error("category", "収入にはカテゴリが必須です。")
            cleaned_data["payment_method"] = None

        if category and transaction_type and category.category_type != transaction_type:
            self.add_error(
                "category", "選択したカテゴリは種別（支出/収入）と一致しません。"
            )

        return cleaned_data


class TransactionFilterForm(forms.Form):
    """画面3 取引一覧の絞り込み条件（基本設計書5.3.2節）。"""

    date_from = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    date_to = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    category = forms.ModelChoiceField(queryset=Category.objects.all(), required=False)
    payment_method = forms.ModelChoiceField(
        queryset=None,
        required=False,
    )
    amount_min = forms.IntegerField(required=False, min_value=0)
    amount_max = forms.IntegerField(required=False, min_value=0)
    counterpart = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from kakeibo.models import PaymentMethod

        self.fields["payment_method"].queryset = PaymentMethod.objects.all()


class CategoryAssignForm(forms.Form):
    """画面5 未分類取引一覧: カテゴリ選択・割当（基本設計書5.3.4節）。"""

    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(category_type=Category.CategoryType.EXPENSE)
    )


class BalanceRecordForm(forms.ModelForm):
    """画面7 残高記録入力（基本設計書5.1.1節）。

    要件4.6.3（同一口座・同一基準日は上書き）に対応するため、呼び出し側
    （ビュー）は既存レコードがあればform_kwargsの`instance`にそれを渡す。
    """

    class Meta:
        model = BalanceRecord
        fields = ("account", "recorded_date", "balance")
        widgets = {
            "recorded_date": forms.DateInput(attrs={"type": "date"}),
        }
