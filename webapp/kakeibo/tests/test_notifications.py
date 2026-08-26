from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from kakeibo.notifications import notify_admin


@override_settings(
    NOTIFICATION_RECIPIENT_EMAIL="family@example.com",
    GMAIL_API_CLIENT_ID="client-id",
    GMAIL_API_CLIENT_SECRET="client-secret",
    GMAIL_API_REFRESH_TOKEN="refresh-token",
)
class NotifyAdminTests(TestCase):
    @patch("kakeibo.notifications.build_gmail_service")
    def test_sends_message_via_gmail_api(self, mock_build_service):
        mock_service = MagicMock()
        mock_build_service.return_value = mock_service

        result = notify_admin("バッチ異常終了", "詳細メッセージ")

        self.assertTrue(result)
        mock_service.users.return_value.messages.return_value.send.assert_called_once()
        _, kwargs = mock_service.users.return_value.messages.return_value.send.call_args
        self.assertEqual(kwargs["userId"], "me")
        self.assertIn("raw", kwargs["body"])

    @patch("kakeibo.notifications.build_gmail_service")
    def test_returns_false_and_does_not_raise_on_api_error(self, mock_build_service):
        mock_build_service.side_effect = RuntimeError("api error")

        result = notify_admin("件名", "本文")

        self.assertFalse(result)

    @override_settings(NOTIFICATION_RECIPIENT_EMAIL="")
    def test_returns_false_when_recipient_not_configured(self):
        result = notify_admin("件名", "本文")
        self.assertFalse(result)
