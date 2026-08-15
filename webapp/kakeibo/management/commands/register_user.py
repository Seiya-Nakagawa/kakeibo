from django.core.management.base import BaseCommand, CommandError

from kakeibo.models import User


class Command(BaseCommand):
    """要件4.9.2: 事前に登録した利用者のみログインを許可する、の事前登録を行う。"""

    help = "ログインを許可する利用者を事前登録する（Googleログイン前に実行する）"

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("display_name")
        parser.add_argument(
            "--role",
            choices=[User.Role.ADMIN, User.Role.GENERAL],
            default=User.Role.GENERAL,
        )

    def handle(self, *args, **options):
        email = options["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f"既に登録済みのメールアドレスです: {email}")

        user = User.objects.create_user(
            email=email,
            display_name=options["display_name"],
            role=options["role"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"登録しました: {user.email} ({user.get_role_display()})"
            )
        )
