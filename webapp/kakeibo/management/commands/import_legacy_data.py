from django.core.management.base import BaseCommand, CommandError

from kakeibo.legacy_import import (
    LegacyImportError,
    import_categories,
    import_fixed_costs,
    import_store_rules,
    import_transactions,
    verify_transactions,
)
from kakeibo.models import User


class Command(BaseCommand):
    """要件4.10: 現行スプレッドシートのデータを一括投入する（基本設計書6.3節）。

    CSVはGoogleスプレッドシートから「ファイル > ダウンロード > カンマ区切り形式(.csv)」で
    エクスポートしたものをそのまま指定する（列の並び替えはしないこと）。
    複数のオプションを同時に指定した場合、カテゴリ→店舗ルール→固定費→生データの順に処理する。
    参照先マスタ（カテゴリ・決済手段）が未登録の場合はエラーで中断するため、
    カテゴリ・決済手段・口座マスタは事前に登録しておくこと（Issue #53）。
    """

    help = "現行スプレッドシートのCSVエクスポートから、カテゴリ・店舗ルール・固定費・生データを一括投入する"

    def add_arguments(self, parser):
        parser.add_argument(
            "--categories", help="カテゴリ（月次集計シートA〜C列）のCSVパス"
        )
        parser.add_argument("--store-rules", help="店舗ルールシートのCSVパス")
        parser.add_argument("--fixed-costs", help="固定費マスタシートのCSVパス")
        parser.add_argument("--transactions", help="生データシートのCSVパス")
        parser.add_argument(
            "--imported-by",
            help="生データ移行時、取引のcreated_byとして記録する利用者のメールアドレス"
            "（--transactions指定時は必須）",
        )

    def handle(self, *args, **options):
        try:
            self._run(options)
        except LegacyImportError as exc:
            raise CommandError(str(exc)) from exc

    def _run(self, options):
        if options["categories"]:
            result = import_categories(options["categories"])
            self._report("カテゴリ", result)

        if options["store_rules"]:
            result = import_store_rules(options["store_rules"])
            self._report("店舗ルール", result)

        if options["fixed_costs"]:
            result = import_fixed_costs(options["fixed_costs"])
            self._report("固定費", result)

        if options["transactions"]:
            self._run_transactions(options)

    def _run_transactions(self, options):
        if not options["imported_by"]:
            raise CommandError("--transactions指定時は--imported-byが必須です")
        imported_by = self._resolve_user(options["imported_by"])
        result = import_transactions(options["transactions"], imported_by)
        self.stdout.write(
            self.style.SUCCESS(
                f"生データ: 新規{result.created}件、重複スキップ{result.skipped_duplicate}件、"
                f"固定費行スキップ{result.skipped_fixed}件"
            )
        )
        self._report_verification(result)

    def _resolve_user(self, email) -> User:
        try:
            return User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise CommandError(
                f"--imported-byに一致する利用者がいません: {email}"
            ) from exc

    def _report(self, label, result):
        self.stdout.write(
            self.style.SUCCESS(
                f"{label}: 新規{result.created}件、更新{result.updated}件"
            )
        )

    def _report_verification(self, result):
        # 要件4.10.3: 件数・月次合計金額の一致検証。
        verifications = verify_transactions(result)
        for v in verifications:
            self.stdout.write(
                f"  {v.month}: 件数 CSV={v.csv_count} DB={v.db_count} / "
                f"合計 CSV={v.csv_total}円 DB={v.db_total}円"
            )

        mismatches = [v for v in verifications if not v.matches]
        if mismatches:
            raise CommandError(
                "月次の件数・合計金額がCSVとDBで一致しません: "
                + "、".join(v.month for v in mismatches)
            )
        self.stdout.write(
            self.style.SUCCESS("月次の件数・合計金額が一致することを確認しました")
        )
