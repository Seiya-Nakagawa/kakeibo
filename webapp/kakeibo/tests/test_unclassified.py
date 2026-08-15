from django.test import Client, TestCase
from django.urls import reverse

from kakeibo.models import Category, StoreRule, Transaction, User


class UnclassifiedTransactionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="user@example.com", display_name="利用者", role=User.Role.GENERAL
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.category = Category.objects.create(
            name="食費", category_type=Category.CategoryType.EXPENSE
        )
        self.transaction = Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date="2026-08-01",
            amount=1000,
            counterpart="セブン-イレブン新宿三丁目店",
            source=Transaction.Source.MANUAL,
            created_by=self.user,
        )

    def test_list_shows_only_unclassified_expense(self):
        Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date="2026-08-01",
            amount=2000,
            counterpart="分類済み",
            category=self.category,
            source=Transaction.Source.MANUAL,
            created_by=self.user,
        )
        response = self.client.get(reverse("unclassified-transaction-list"))
        self.assertEqual(len(response.context["transactions"]), 1)
        self.assertEqual(response.context["transactions"][0], self.transaction)

    def test_assign_category_sets_category_and_learns_rule(self):
        response = self.client.post(
            reverse("transaction-assign-category", args=[self.transaction.pk]),
            {"category": self.category.pk},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.category, self.category)
        rule = StoreRule.objects.get(keyword="セブン-イレブン新宿三丁目店")
        self.assertTrue(rule.is_auto_generated)
        self.assertEqual(rule.category, self.category)

    def test_next_import_with_same_store_is_auto_classified(self):
        self.client.post(
            reverse("transaction-assign-category", args=[self.transaction.pk]),
            {"category": self.category.pk},
        )
        from kakeibo.categorization import match_category

        self.assertEqual(match_category("セブン-イレブン新宿三丁目店"), self.category)
