from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
from django.shortcuts import redirect


class AccountAdapter(DefaultAccountAdapter):
    """ローカル（メール/パスワード）のサインアップは提供しない。"""

    def is_open_for_signup(self, request):
        return False


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """要件4.9.2: 事前登録した利用者のみログインを許可する。"""

    def is_open_for_signup(self, request, sociallogin):
        return False

    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return

        email = sociallogin.user.email
        User = get_user_model()
        try:
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            raise ImmediateHttpResponse(redirect("account-denied"))

        sociallogin.connect(request, user)
        google_sub = sociallogin.account.uid
        if not user.google_sub:
            user.google_sub = google_sub
            user.save(update_fields=["google_sub"])
