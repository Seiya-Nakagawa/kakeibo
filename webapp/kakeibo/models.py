from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """パスワードを持たない（Google OAuth専用）利用者のマネージャ。"""

    def create_user(self, email, display_name, role=None, **extra_fields):
        if not email:
            raise ValueError("email is required")
        user = self.model(
            email=self.normalize_email(email),
            display_name=display_name,
            role=role or User.Role.GENERAL,
            **extra_fields,
        )
        user.set_unusable_password()
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    """家計簿を利用する家族メンバー（Google OAuthでログイン）。"""

    class Role(models.TextChoices):
        ADMIN = "admin", "管理者"
        GENERAL = "general", "一般"

    # 事前登録時点ではGoogle側のsubが不明なため、初回ログイン成功時に設定する。
    google_sub = models.CharField(
        "Google識別子", max_length=255, unique=True, null=True, blank=True
    )
    email = models.EmailField("メールアドレス", max_length=255, unique=True)
    display_name = models.CharField("表示名", max_length=100)
    role = models.CharField(
        "権限", max_length=20, choices=Role.choices, default=Role.GENERAL
    )
    is_active = models.BooleanField("有効", default=True)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]

    class Meta:
        verbose_name = "利用者"
        verbose_name_plural = "利用者"

    def __str__(self):
        return self.display_name

    # PermissionsMixinは使わず、role（admin/general）のみで権限を判定する。
    # groups/permissionsテーブルは本システムの権限設計（2段階）では不要なため導入しない。
    @property
    def is_staff(self):
        return self.role == self.Role.ADMIN

    @property
    def is_superuser(self):
        return self.role == self.Role.ADMIN

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser


class Category(models.Model):
    """支出・収入のカテゴリ。"""

    class CategoryType(models.TextChoices):
        EXPENSE = "expense", "支出"
        INCOME = "income", "収入"

    name = models.CharField("カテゴリ名", max_length=50)
    category_type = models.CharField("種別", max_length=20, choices=CategoryType.choices)
    monthly_budget = models.IntegerField("月次予算", null=True, blank=True)
    is_aggregated = models.BooleanField("集計対象", default=True)
    display_order = models.IntegerField("表示順", default=0)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "カテゴリ"
        verbose_name_plural = "カテゴリ"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "category_type"],
                name="uq_category_name_type",
            ),
        ]

    def __str__(self):
        return self.name


class StoreRule(models.Model):
    """店舗名キーワードとカテゴリの自動割当ルール。"""

    keyword = models.CharField("キーワード", max_length=100, unique=True)
    category = models.ForeignKey(Category, verbose_name="カテゴリ", on_delete=models.PROTECT)
    priority = models.IntegerField("優先度")
    is_auto_generated = models.BooleanField("自動生成", default=False)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "店舗ルール"
        verbose_name_plural = "店舗ルール"

    def __str__(self):
        return self.keyword


class PaymentMethod(models.Model):
    """決済手段マスタ。"""

    name = models.CharField("決済手段名", max_length=50, unique=True)
    display_order = models.IntegerField("表示順", default=0)
    is_active = models.BooleanField("有効", default=True)

    class Meta:
        verbose_name = "決済手段"
        verbose_name_plural = "決済手段"

    def __str__(self):
        return self.name


class Account(models.Model):
    """口座マスタ。"""

    class AccountType(models.TextChoices):
        BANK = "bank", "銀行"
        SECURITIES = "securities", "証券"
        EMONEY = "emoney", "電子マネー"
        CASH = "cash", "現金"
        OTHER = "other", "その他"

    name = models.CharField("口座名", max_length=50)
    account_type = models.CharField("種別", max_length=20, choices=AccountType.choices)
    currency = models.CharField("通貨", max_length=3, default="JPY")
    display_order = models.IntegerField("表示順", default=0)
    is_active = models.BooleanField("有効", default=True)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "口座"
        verbose_name_plural = "口座"

    def __str__(self):
        return self.name


class BalanceRecord(models.Model):
    """口座の残高記録。"""

    account = models.ForeignKey(Account, verbose_name="口座", on_delete=models.PROTECT)
    recorded_date = models.DateField("記録日")
    balance = models.IntegerField("残高")
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "残高記録"
        verbose_name_plural = "残高記録"
        constraints = [
            models.UniqueConstraint(
                fields=["account", "recorded_date"],
                name="uq_balance_record_account_date",
            ),
        ]

    def __str__(self):
        return f"{self.account} / {self.recorded_date}"


class FixedCost(models.Model):
    """固定費の定義。"""

    payee = models.CharField("支払先", max_length=100)
    amount = models.IntegerField("金額")
    category = models.ForeignKey(Category, verbose_name="カテゴリ", on_delete=models.PROTECT)
    payment_method = models.ForeignKey(
        PaymentMethod, verbose_name="決済手段", on_delete=models.PROTECT
    )
    start_month = models.DateField("開始月")
    end_month = models.DateField("終了月", null=True, blank=True)
    memo = models.CharField("メモ", max_length=255, null=True, blank=True)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "固定費"
        verbose_name_plural = "固定費"

    def __str__(self):
        return self.payee


class FixedIncome(models.Model):
    """固定収入の定義。"""

    source = models.CharField("収入元", max_length=100)
    amount = models.IntegerField("金額")
    category = models.ForeignKey(Category, verbose_name="カテゴリ", on_delete=models.PROTECT)
    account = models.ForeignKey(Account, verbose_name="入金先口座", on_delete=models.PROTECT)
    start_month = models.DateField("開始月")
    end_month = models.DateField("終了月", null=True, blank=True)
    memo = models.CharField("メモ", max_length=255, null=True, blank=True)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "固定収入"
        verbose_name_plural = "固定収入"

    def __str__(self):
        return self.source


class Transaction(models.Model):
    """支出・収入の取引。"""

    class TransactionType(models.TextChoices):
        EXPENSE = "expense", "支出"
        INCOME = "income", "収入"

    class Source(models.TextChoices):
        MAIL = "mail", "メール取込"
        MANUAL = "manual", "手動入力"

    transaction_type = models.CharField(
        "種別", max_length=20, choices=TransactionType.choices
    )
    transaction_date = models.DateField("日付", db_index=True)
    amount = models.IntegerField("金額")
    counterpart = models.CharField("店舗名・収入元", max_length=100)
    category = models.ForeignKey(
        Category,
        verbose_name="カテゴリ",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    payment_method = models.ForeignKey(
        PaymentMethod,
        verbose_name="決済手段",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    account = models.ForeignKey(
        Account,
        verbose_name="入金先口座",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    memo = models.CharField("メモ", max_length=255, null=True, blank=True)
    source = models.CharField("取込元", max_length=20, choices=Source.choices)
    dedup_hash = models.CharField(
        "重複判定ハッシュ", max_length=64, null=True, blank=True, unique=True
    )
    is_excluded_from_aggregation = models.BooleanField("除外フラグ", default=False)
    is_deleted = models.BooleanField("削除済み", default=False)
    created_by = models.ForeignKey(User, verbose_name="登録者", on_delete=models.PROTECT)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "取引"
        verbose_name_plural = "取引"
        indexes = [
            models.Index(fields=["transaction_type"]),
        ]

    def __str__(self):
        return f"{self.transaction_date} {self.counterpart} {self.amount}"


class EmailImportLog(models.Model):
    """メール取込の実行ログ。"""

    class Status(models.TextChoices):
        SUCCESS = "success", "成功"
        FAILED = "failed", "失敗"

    gmail_message_id = models.CharField("Gmailメッセージ ID", max_length=100, unique=True)
    service = models.CharField("サービス", max_length=50, null=True, blank=True)
    status = models.CharField("ステータス", max_length=20, choices=Status.choices)
    error_detail = models.CharField(
        "エラー詳細", max_length=500, null=True, blank=True
    )
    executed_at = models.DateTimeField("実行日時")

    class Meta:
        verbose_name = "メール取込ログ"
        verbose_name_plural = "メール取込ログ"

    def __str__(self):
        return self.gmail_message_id
