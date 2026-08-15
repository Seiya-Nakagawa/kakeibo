from django.contrib import admin
from django.urls import include, path

from kakeibo import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("access-denied/", views.AccessDeniedView.as_view(), name="account-denied"),
    path("", views.HomeView.as_view(), name="home"),
    # 以下3件はnavigation実装のため先行してURL名を予約する。実体は各Issueで置き換える。
    path("dashboard-placeholder/", views.HomeView.as_view(), name="dashboard"),
    path(
        "unclassified-placeholder/",
        views.HomeView.as_view(),
        name="unclassified-transaction-list",
    ),
    path("balance-placeholder/", views.HomeView.as_view(), name="account-balance"),
    path("transactions/", views.TransactionListView.as_view(), name="transaction-list"),
    path(
        "transactions/export/",
        views.TransactionExportCsvView.as_view(),
        name="transaction-export-csv",
    ),
    path(
        "transactions/new/",
        views.TransactionCreateView.as_view(),
        name="transaction-create",
    ),
    path(
        "transactions/<int:pk>/edit/",
        views.TransactionUpdateView.as_view(),
        name="transaction-update",
    ),
    path(
        "transactions/<int:pk>/delete/",
        views.TransactionDeleteView.as_view(),
        name="transaction-delete",
    ),
]
