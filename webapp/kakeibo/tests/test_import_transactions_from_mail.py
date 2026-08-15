import base64
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from kakeibo.mail_import import compute_dedup_hash
from kakeibo.models import EmailImportLog, PaymentMethod, Transaction, User

COMMAND_MODULE = "kakeibo.management.commands.import_transactions_from_mail"

LABELS_RESPONSE = {
    "labels": [
        {"name": "家計簿/未処理", "id": "LABEL_UNPROCESSED"},
        {"name": "家計簿/処理済", "id": "LABEL_PROCESSED"},
    ]
}


def _encode(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _make_message(message_id, sender, subject, body_text):
    return {
        "id": message_id,
        "payload": {
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
            ],
            "mimeType": "text/plain",
            "body": {"data": _encode(body_text)},
        },
    }


class _FakeExecute:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _FakeMessages:
    def __init__(self, messages_by_id, modify_calls):
        self._messages_by_id = messages_by_id
        self._modify_calls = modify_calls

    def list(self, **kwargs):
        return _FakeExecute({"messages": [{"id": mid} for mid in self._messages_by_id]})

    def get(self, **kwargs):
        return _FakeExecute(self._messages_by_id[kwargs["id"]])

    def modify(self, **kwargs):
        self._modify_calls.append(kwargs)
        return _FakeExecute({})


class _FakeLabels:
    def __init__(self, labels_response):
        self._labels_response = labels_response

    def list(self, **kwargs):
        return _FakeExecute(self._labels_response)


class FakeGmailService:
    def __init__(self, messages_by_id, labels_response=LABELS_RESPONSE):
        self.modify_calls = []
        self._messages = _FakeMessages(messages_by_id, self.modify_calls)
        self._labels = _FakeLabels(labels_response)

    def users(self):
        return self

    def messages(self):
        return self._messages

    def labels(self):
        return self._labels


@override_settings(MAIL_IMPORT_USER_EMAIL="import-bot@example.com")
class ImportTransactionsFromMailTests(TestCase):
    def setUp(self):
        self.import_user = User.objects.create_user(
            email="import-bot@example.com",
            display_name="取込担当",
            role=User.Role.ADMIN,
        )
        self.payment_method = PaymentMethod.objects.create(name="楽天ペイ")

    @patch(f"{COMMAND_MODULE}.notify_admin")
    @patch(f"{COMMAND_MODULE}.build_gmail_service")
    def test_successful_import_creates_transaction_and_switches_label(
        self, mock_build_service, mock_notify
    ):
        body = (
            "■利用日時：2026/08/10 12:34\n"
            "■利用店舗：セブン-イレブン新宿三丁目店\n"
            "■利用金額：1,000円\n"
        )
        message = _make_message(
            "msg-1",
            "no-reply@pay.rakuten.co.jp",
            "楽天ペイアプリご利用内容のお知らせ",
            body,
        )
        fake_service = FakeGmailService({"msg-1": message})
        mock_build_service.return_value = fake_service

        call_command("import_transactions_from_mail")

        transaction = Transaction.objects.get()
        self.assertEqual(transaction.amount, 1000)
        self.assertEqual(transaction.counterpart, "セブン-イレブン新宿三丁目店")
        self.assertEqual(transaction.payment_method, self.payment_method)
        self.assertEqual(transaction.source, Transaction.Source.MAIL)
        self.assertEqual(transaction.created_by, self.import_user)

        log = EmailImportLog.objects.get(gmail_message_id="msg-1")
        self.assertEqual(log.status, EmailImportLog.Status.SUCCESS)

        self.assertEqual(len(fake_service.modify_calls), 1)
        modify_kwargs = fake_service.modify_calls[0]
        self.assertEqual(modify_kwargs["body"]["removeLabelIds"], ["LABEL_UNPROCESSED"])
        self.assertEqual(modify_kwargs["body"]["addLabelIds"], ["LABEL_PROCESSED"])
        mock_notify.assert_not_called()

    @patch(f"{COMMAND_MODULE}.notify_admin")
    @patch(f"{COMMAND_MODULE}.build_gmail_service")
    def test_unidentifiable_sender_logs_failure_and_notifies(
        self, mock_build_service, mock_notify
    ):
        message = _make_message("msg-2", "unknown@example.com", "無関係の件名", "本文")
        fake_service = FakeGmailService({"msg-2": message})
        mock_build_service.return_value = fake_service

        call_command("import_transactions_from_mail")

        self.assertEqual(Transaction.objects.count(), 0)
        log = EmailImportLog.objects.get(gmail_message_id="msg-2")
        self.assertEqual(log.status, EmailImportLog.Status.FAILED)
        self.assertEqual(fake_service.modify_calls, [])
        mock_notify.assert_called_once()

    @patch(f"{COMMAND_MODULE}.notify_admin")
    @patch(f"{COMMAND_MODULE}.build_gmail_service")
    def test_missing_payment_method_master_is_logged_as_failure(
        self, mock_build_service, mock_notify
    ):
        self.payment_method.delete()
        body = "■利用日時：2026/08/10 12:34\n■利用店舗：店舗\n■利用金額：1,000円\n"
        message = _make_message(
            "msg-3",
            "no-reply@pay.rakuten.co.jp",
            "楽天ペイアプリご利用内容のお知らせ",
            body,
        )
        fake_service = FakeGmailService({"msg-3": message})
        mock_build_service.return_value = fake_service

        call_command("import_transactions_from_mail")

        self.assertEqual(Transaction.objects.count(), 0)
        log = EmailImportLog.objects.get(gmail_message_id="msg-3")
        self.assertEqual(log.status, EmailImportLog.Status.FAILED)
        self.assertIn("決済手段マスタ", log.error_detail)

    @patch(f"{COMMAND_MODULE}.notify_admin")
    @patch(f"{COMMAND_MODULE}.build_gmail_service")
    def test_duplicate_transaction_is_skipped_but_message_marked_processed(
        self, mock_build_service, mock_notify
    ):
        from datetime import date

        dedup_hash = compute_dedup_hash(date(2026, 8, 10), 1000, "既存店舗", "楽天ペイ")
        Transaction.objects.create(
            transaction_type=Transaction.TransactionType.EXPENSE,
            transaction_date=date(2026, 8, 10),
            amount=1000,
            counterpart="既存店舗",
            payment_method=self.payment_method,
            source=Transaction.Source.MAIL,
            dedup_hash=dedup_hash,
            created_by=self.import_user,
        )
        body = "■利用日時：2026/08/10 12:34\n■利用店舗：既存店舗\n■利用金額：1,000円\n"
        message = _make_message(
            "msg-4",
            "no-reply@pay.rakuten.co.jp",
            "楽天ペイアプリご利用内容のお知らせ",
            body,
        )
        fake_service = FakeGmailService({"msg-4": message})
        mock_build_service.return_value = fake_service

        call_command("import_transactions_from_mail")

        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(len(fake_service.modify_calls), 1)
        log = EmailImportLog.objects.get(gmail_message_id="msg-4")
        self.assertEqual(log.status, EmailImportLog.Status.SUCCESS)

    @patch(f"{COMMAND_MODULE}.notify_admin")
    @patch(f"{COMMAND_MODULE}.build_gmail_service")
    def test_missing_gmail_labels_raises_and_notifies(
        self, mock_build_service, mock_notify
    ):
        fake_service = FakeGmailService({}, labels_response={"labels": []})
        mock_build_service.return_value = fake_service

        with self.assertRaises(CommandError):
            call_command("import_transactions_from_mail")

        mock_notify.assert_called_once()

    @patch(f"{COMMAND_MODULE}.notify_admin")
    def test_missing_import_user_setting_raises_before_calling_gmail(self, mock_notify):
        with (
            override_settings(MAIL_IMPORT_USER_EMAIL=""),
            self.assertRaises(CommandError),
        ):
            call_command("import_transactions_from_mail")
        mock_notify.assert_called_once()
