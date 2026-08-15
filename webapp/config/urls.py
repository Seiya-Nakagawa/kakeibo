from django.contrib import admin
from django.urls import include, path

from kakeibo import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("access-denied/", views.AccessDeniedView.as_view(), name="account-denied"),
    path("", views.HomeView.as_view(), name="home"),
]
