from django.contrib.admin.sites import site
from django.test import Client, TestCase
from django.urls import reverse

from kakeibo.models import Account, Category, PaymentMethod, StoreRule, User


class AdminRegistrationTests(TestCase):
    """要件4.8: マスタをAdmin画面から保守できること。"""

    def test_master_models_are_registered(self):
        for model in (Category, StoreRule, PaymentMethod, Account, User):
            self.assertIn(model, site._registry)


class AdminAccessTests(TestCase):
    """基本設計書2.3節: Adminはstaff（admin権限）のみアクセスできること。"""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com", display_name="管理者", role=User.Role.ADMIN
        )
        self.general_user = User.objects.create_user(
            email="general@example.com", display_name="一般", role=User.Role.GENERAL
        )

    def test_admin_role_can_access_admin_site(self):
        client = Client()
        client.force_login(self.admin_user)
        response = client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)

    def test_general_role_cannot_access_admin_site(self):
        client = Client()
        client.force_login(self.general_user)
        response = client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)
