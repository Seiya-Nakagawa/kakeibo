from django.contrib.auth.decorators import login_not_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView


class HomeView(TemplateView):
    """ログイン後の暫定的な遷移先（画面2 ダッシュボードは別Issueで実装）。"""

    template_name = "kakeibo/home.html"


@method_decorator(login_not_required, name="dispatch")
class AccessDeniedView(TemplateView):
    """画面8: 未登録のGoogleアカウントでログインした際に表示する。"""

    template_name = "kakeibo/access_denied.html"
