from django.test import Client, TestCase
from django.urls import reverse

from kakeibo.models import Category, PaymentMethod, Transaction, User


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="user@example.com", display_name="利用者", role=User.Role.GENERAL
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.category = Category.objects.create(
            name="食費",
            category_type=Category.CategoryType.EXPENSE,
            monthly_budget=10000,
        )
        self.payment_method = PaymentMethod.objects.create(name="現金")
        Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date="2026-08-05",
            amount=3000,
            counterpart="店",
            category=self.category,
            payment_method=self.payment_method,
            source=Transaction.Source.MANUAL,
            created_by=self.user,
        )

    def test_dashboard_renders_with_default_month(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["expense_total"], 3000)

    def test_dashboard_accepts_month_query_param(self):
        response = self.client.get(reverse("dashboard"), {"month": "2026-08"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["target_month"].isoformat(), "2026-08-01")

    def test_unclassified_count_shown_when_present(self):
        Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date="2026-08-06",
            amount=500,
            counterpart="未分類店",
            payment_method=self.payment_method,
            source=Transaction.Source.MANUAL,
            created_by=self.user,
        )
        response = self.client.get(reverse("dashboard"), {"month": "2026-08"})
        self.assertEqual(response.context["unclassified_count"], 1)
