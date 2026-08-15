from django.test import Client, TestCase
from django.urls import reverse

from kakeibo.models import Account, BalanceRecord, User


class AccountBalanceViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="user@example.com", display_name="利用者", role=User.Role.GENERAL
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.bank_account = Account.objects.create(
            name="普通預金", account_type=Account.AccountType.BANK, display_order=1
        )
        self.cash_account = Account.objects.create(
            name="現金", account_type=Account.AccountType.CASH, display_order=2
        )
        BalanceRecord.objects.create(
            account=self.bank_account, recorded_date="2026-08-01", balance=100000
        )
        BalanceRecord.objects.create(
            account=self.cash_account, recorded_date="2026-08-01", balance=5000
        )

    def test_summary_shows_total_and_breakdown_by_type(self):
        response = self.client.get(reverse("account-balance"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_assets"], 105000)
        self.assertEqual(response.context["assets_by_type"]["銀行"], 100000)

    def test_inactive_account_is_excluded(self):
        self.cash_account.is_active = False
        self.cash_account.save()
        response = self.client.get(reverse("account-balance"))
        self.assertEqual(response.context["total_assets"], 100000)
        names = [ab.account.name for ab in response.context["account_balances"]]
        self.assertNotIn("現金", names)


class BalanceRecordCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="user@example.com", display_name="利用者", role=User.Role.GENERAL
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.account = Account.objects.create(
            name="普通預金", account_type=Account.AccountType.BANK
        )

    def test_creates_new_record(self):
        response = self.client.post(
            reverse("balance-record-create"),
            {
                "account": self.account.pk,
                "recorded_date": "2026-08-01",
                "balance": 100000,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        record = BalanceRecord.objects.get(
            account=self.account, recorded_date="2026-08-01"
        )
        self.assertEqual(record.balance, 100000)

    def test_reregistering_same_account_and_date_overwrites(self):
        BalanceRecord.objects.create(
            account=self.account, recorded_date="2026-08-01", balance=100000
        )
        self.client.post(
            reverse("balance-record-create"),
            {
                "account": self.account.pk,
                "recorded_date": "2026-08-01",
                "balance": 120000,
            },
        )
        self.assertEqual(BalanceRecord.objects.count(), 1)
        record = BalanceRecord.objects.get(
            account=self.account, recorded_date="2026-08-01"
        )
        self.assertEqual(record.balance, 120000)
