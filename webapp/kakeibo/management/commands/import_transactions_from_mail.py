from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from kakeibo.categorization import match_category
from kakeibo.gmail_client import SCOPE_LABELS, SCOPE_READONLY, build_gmail_service
from kakeibo.mail_import import (
    compute_dedup_hash,
    extract_plain_text,
    header_value,
    identify_service,
    parse_mail_body,
)
from kakeibo.models import EmailImportLog, PaymentMethod, Transaction, User
from kakeibo.notifications import notify_admin

LABEL_UNPROCESSED = "家計簿/未処理"
LABEL_PROCESSED = "家計簿/処理済"


class Command(BaseCommand):
    """要件4.1: Gmailの決済通知メールを取得し取引として登録する（基本設計書3.1節）。"""

    help = "Gmailの決済通知メールを取得し取引として登録する（日次CronJobから実行する）"

    def handle(self, *args, **options):
        try:
            self._run()
        except Exception as exc:
            notify_admin("メール取込バッチが異常終了しました", str(exc))
            raise CommandError(f"メール取込バッチが異常終了しました: {exc}") from exc

    def _run(self):
        import_user = self._resolve_import_user()
        service = build_gmail_service([SCOPE_READONLY, SCOPE_LABELS])
        label_ids = self._label_ids(service)
        message_ids = self._list_target_message_ids(
            service, label_ids[LABEL_UNPROCESSED]
        )

        failures = []
        imported_count = 0
        for message_id in message_ids:
            if EmailImportLog.objects.filter(
                gmail_message_id=message_id, status=EmailImportLog.Status.SUCCESS
            ).exists():
                continue
            error = self._process_message(service, message_id, label_ids, import_user)
            if error:
                failures.append(error)
            else:
                imported_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"取込成功: {imported_count}件、失敗: {len(failures)}件")
        )

        if failures:
            # 要件4.1.2.8: 識別・解析に失敗したメールを特定できる情報を含めて通知する。
            notify_admin(
                f"メール取込で{len(failures)}件のエラーが発生しました",
                "\n\n".join(failures),
            )

    def _resolve_import_user(self) -> User:
        # 基本設計書6.2節: メール取込は対話的なログインユーザーが存在しないため、
        # 環境変数で指定した利用者をcreated_by（登録者）として記録する。
        if not settings.MAIL_IMPORT_USER_EMAIL:
            raise CommandError("MAIL_IMPORT_USER_EMAILが未設定です")
        try:
            return User.objects.get(email__iexact=settings.MAIL_IMPORT_USER_EMAIL)
        except User.DoesNotExist as exc:
            raise CommandError(
                "MAIL_IMPORT_USER_EMAILに一致する利用者がいません: "
                f"{settings.MAIL_IMPORT_USER_EMAIL}"
            ) from exc

    def _label_ids(self, service) -> dict:
        response = service.users().labels().list(userId="me").execute()
        by_name = {label["name"]: label["id"] for label in response.get("labels", [])}
        missing = [
            name for name in (LABEL_UNPROCESSED, LABEL_PROCESSED) if name not in by_name
        ]
        if missing:
            raise CommandError(
                f"Gmailに以下のラベルが存在しません: {', '.join(missing)}"
            )
        return by_name

    def _list_target_message_ids(self, service, unprocessed_label_id) -> list:
        message_ids = []
        page_token = None
        while True:
            kwargs = {"userId": "me", "labelIds": [unprocessed_label_id]}
            if page_token:
                kwargs["pageToken"] = page_token
            response = service.users().messages().list(**kwargs).execute()
            message_ids.extend(m["id"] for m in response.get("messages", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return message_ids

    def _process_message(
        self, service, message_id, label_ids, import_user
    ) -> str | None:
        """処理に失敗した場合は通知用のエラーメッセージを返す。成功時はNoneを返す。"""
        message = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = message.get("payload", {})
        sender = header_value(payload, "From")
        subject = header_value(payload, "Subject")

        rule = identify_service(sender, subject)
        if rule is None:
            self._log_result(
                message_id,
                None,
                EmailImportLog.Status.FAILED,
                "サービスを識別できませんでした",
            )
            return f"message_id={message_id} subject={subject!r}: サービスを識別できませんでした"

        body = extract_plain_text(payload)
        items = parse_mail_body(body)
        if not items:
            self._log_result(
                message_id,
                rule.service,
                EmailImportLog.Status.FAILED,
                "本文の解析に失敗しました（明細が抽出できません）",
            )
            return (
                f"message_id={message_id} subject={subject!r} service={rule.service}: "
                "本文の解析に失敗しました"
            )

        try:
            payment_method = PaymentMethod.objects.get(name=rule.payment_method_name)
        except PaymentMethod.DoesNotExist:
            error_detail = f"決済手段マスタ未登録: {rule.payment_method_name}"
            self._log_result(
                message_id, rule.service, EmailImportLog.Status.FAILED, error_detail
            )
            return f"message_id={message_id} service={rule.service}: {error_detail}"

        for item in items:
            dedup_hash = compute_dedup_hash(
                item.transaction_date,
                item.amount,
                item.counterpart,
                payment_method.name,
            )
            # 基本設計書3.1.3節: 取引単位の重複排除。
            if Transaction.objects.filter(dedup_hash=dedup_hash).exists():
                continue
            Transaction.objects.create(
                transaction_type=Transaction.TransactionType.EXPENSE,
                transaction_date=item.transaction_date,
                amount=item.amount,
                counterpart=item.counterpart,
                category=match_category(item.counterpart),
                payment_method=payment_method,
                source=Transaction.Source.MAIL,
                dedup_hash=dedup_hash,
                created_by=import_user,
            )

        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={
                "removeLabelIds": [label_ids[LABEL_UNPROCESSED]],
                "addLabelIds": [label_ids[LABEL_PROCESSED]],
            },
        ).execute()
        self._log_result(message_id, rule.service, EmailImportLog.Status.SUCCESS, None)
        return None

    def _log_result(self, message_id, service_name, status, error_detail):
        # gmail_message_idはUNIQUEのため、再処理時は同一行を更新する
        # （基本設計書3.1.3節: メール単位の重複排除に用いる状態記録）。
        EmailImportLog.objects.update_or_create(
            gmail_message_id=message_id,
            defaults={
                "service": service_name,
                "status": status,
                "error_detail": error_detail,
                "executed_at": timezone.now(),
            },
        )
