from django.test import Client, TestCase
from django.urls import reverse

from kakeibo.models import Account, Category, PaymentMethod, Transaction, User


class TransactionViewTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="user@example.com", display_name="利用者", role=User.Role.GENERAL
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.expense_category = Category.objects.create(
            name="食費", category_type=Category.CategoryType.EXPENSE
        )
        self.income_category = Category.objects.create(
            name="給与", category_type=Category.CategoryType.INCOME
        )
        self.payment_method = PaymentMethod.objects.create(name="現金")
        self.account = Account.objects.create(
            name="普通預金", account_type=Account.AccountType.BANK
        )


class TransactionCreateViewTests(TransactionViewTestBase):
    def test_create_expense_requires_payment_method(self):
        response = self.client.post(
            reverse("transaction-create"),
            {
                "transaction_type": Transaction.TransactionType.EXPENSE,
                "transaction_date": "2026-08-01",
                "amount": "1000",
                "counterpart": "スーパー",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "payment_method", "支出には決済手段が必須です。"
        )

    def test_create_expense_success_sets_source_and_created_by(self):
        response = self.client.post(
            reverse("transaction-create"),
            {
                "transaction_type": Transaction.TransactionType.EXPENSE,
                "transaction_date": "2026-08-01",
                "amount": "1000",
                "counterpart": "スーパー",
                "payment_method": self.payment_method.pk,
                "category": self.expense_category.pk,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        transaction = Transaction.objects.get()
        self.assertEqual(transaction.source, Transaction.Source.MANUAL)
        self.assertEqual(transaction.created_by, self.user)
        self.assertEqual(transaction.payment_method, self.payment_method)
        self.assertIsNone(transaction.account)

    def test_create_income_requires_account_and_category(self):
        response = self.client.post(
            reverse("transaction-create"),
            {
                "transaction_type": Transaction.TransactionType.INCOME,
                "transaction_date": "2026-08-01",
                "amount": "300000",
                "counterpart": "勤務先",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "account", "収入には入金先口座が必須です。"
        )
        self.assertFormError(
            response.context["form"], "category", "収入にはカテゴリが必須です。"
        )

    def test_category_type_mismatch_is_rejected(self):
        response = self.client.post(
            reverse("transaction-create"),
            {
                "transaction_type": Transaction.TransactionType.EXPENSE,
                "transaction_date": "2026-08-01",
                "amount": "1000",
                "counterpart": "スーパー",
                "payment_method": self.payment_method.pk,
                "category": self.income_category.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "category",
            "選択したカテゴリは種別（支出/収入）と一致しません。",
        )


class TransactionListViewTests(TransactionViewTestBase):
    def setUp(self):
        super().setUp()
        Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date="2026-08-01",
            amount=1000,
            counterpart="スーパーA",
            category=self.expense_category,
            payment_method=self.payment_method,
            source=Transaction.Source.MANUAL,
            created_by=self.user,
        )
        Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date="2026-08-02",
            amount=5000,
            counterpart="スーパーB",
            category=self.expense_category,
            payment_method=self.payment_method,
            source=Transaction.Source.MANUAL,
            created_by=self.user,
            is_deleted=True,
        )

    def test_deleted_transactions_are_excluded(self):
        response = self.client.get(reverse("transaction-list"))
        self.assertEqual(len(response.context["transactions"]), 1)

    def test_amount_filter(self):
        response = self.client.get(reverse("transaction-list"), {"amount_min": "2000"})
        self.assertEqual(len(response.context["transactions"]), 0)

    def test_csv_export(self):
        response = self.client.get(reverse("transaction-export-csv"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        self.assertIn("スーパーA", content)
        self.assertNotIn("スーパーB", content)


class TransactionDeleteViewTests(TransactionViewTestBase):
    def test_delete_is_logical(self):
        transaction = Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date="2026-08-01",
            amount=1000,
            counterpart="スーパー",
            category=self.expense_category,
            payment_method=self.payment_method,
            source=Transaction.Source.MANUAL,
            created_by=self.user,
        )
        self.client.post(reverse("transaction-delete", args=[transaction.pk]))
        transaction.refresh_from_db()
        self.assertTrue(transaction.is_deleted)
