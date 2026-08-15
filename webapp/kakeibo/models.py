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
    google_sub = models.CharField(max_length=255, unique=True, null=True, blank=True)
    email = models.EmailField(max_length=255, unique=True)
    display_name = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.GENERAL)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]

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

    name = models.CharField(max_length=50)
    category_type = models.CharField(max_length=20, choices=CategoryType.choices)
    monthly_budget = models.IntegerField(null=True, blank=True)
    is_aggregated = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
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

    keyword = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    priority = models.IntegerField()
    is_auto_generated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.keyword


class PaymentMethod(models.Model):
    """決済手段マスタ。"""

    name = models.CharField(max_length=50, unique=True)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

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

    name = models.CharField(max_length=50)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    currency = models.CharField(max_length=3, default="JPY")
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class BalanceRecord(models.Model):
    """口座の残高記録。"""

    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    recorded_date = models.DateField()
    balance = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
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

    payee = models.CharField(max_length=100)
    amount = models.IntegerField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    start_month = models.DateField()
    end_month = models.DateField(null=True, blank=True)
    memo = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.payee


class FixedIncome(models.Model):
    """固定収入の定義。"""

    source = models.CharField(max_length=100)
    amount = models.IntegerField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    start_month = models.DateField()
    end_month = models.DateField(null=True, blank=True)
    memo = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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

    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    transaction_date = models.DateField(db_index=True)
    amount = models.IntegerField()
    counterpart = models.CharField(max_length=100)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    memo = models.CharField(max_length=255, null=True, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices)
    dedup_hash = models.CharField(max_length=64, null=True, blank=True, unique=True)
    is_excluded_from_aggregation = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
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

    gmail_message_id = models.CharField(max_length=100, unique=True)
    service = models.CharField(max_length=50, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    error_detail = models.CharField(max_length=500, null=True, blank=True)
    executed_at = models.DateTimeField()

    def __str__(self):
        return self.gmail_message_id
