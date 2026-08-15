import gzip
import subprocess
from unittest.mock import MagicMock, patch

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

COMMAND_MODULE = "kakeibo.management.commands.backup_database"

BASE_SETTINGS = {
    "BACKUP_S3_ENDPOINT_URL": "https://example.compat.objectstorage.example.com",
    "BACKUP_S3_ACCESS_KEY": "access-key",
    "BACKUP_S3_SECRET_KEY": "secret-key",
    "BACKUP_S3_REGION": "ap-tokyo-1",
    "BACKUP_BUCKET_NAME": "kakeibo-backups",
}


def _fake_dump_result(content: bytes) -> MagicMock:
    result = MagicMock()
    result.stdout = content
    return result


@override_settings(**BASE_SETTINGS)
class BackupDatabaseTests(TestCase):
    @patch(f"{COMMAND_MODULE}.boto3")
    @patch(f"{COMMAND_MODULE}.subprocess")
    def test_uploads_daily_backup_gzip_compressed(self, mock_subprocess, mock_boto3):
        mock_subprocess.run.return_value = _fake_dump_result(b"-- dump content --")
        fake_client = MagicMock()
        fake_client.list_objects_v2.return_value = {"Contents": []}
        mock_boto3.client.return_value = fake_client

        call_command("backup_database")

        fake_client.put_object.assert_any_call(
            Bucket="kakeibo-backups",
            Key=self._expected_daily_key(),
            Body=gzip.compress(b"-- dump content --"),
        )

    def _expected_daily_key(self):
        from django.utils import timezone

        now = timezone.localtime()
        return f"backups/daily/{now:%Y-%m-%d}.sql.gz"

    @patch(f"{COMMAND_MODULE}.boto3")
    @patch(f"{COMMAND_MODULE}.subprocess")
    @patch(f"{COMMAND_MODULE}.timezone")
    def test_uploads_monthly_backup_on_first_of_month(
        self, mock_timezone, mock_subprocess, mock_boto3
    ):
        from datetime import UTC, datetime

        mock_timezone.localtime.return_value = datetime(2026, 8, 1, 3, 0, 0, tzinfo=UTC)
        mock_subprocess.run.return_value = _fake_dump_result(b"dump")
        fake_client = MagicMock()
        fake_client.list_objects_v2.return_value = {"Contents": []}
        mock_boto3.client.return_value = fake_client

        call_command("backup_database")

        fake_client.put_object.assert_any_call(
            Bucket="kakeibo-backups",
            Key="backups/monthly/2026-08.sql.gz",
            Body=gzip.compress(b"dump"),
        )

    @patch(f"{COMMAND_MODULE}.boto3")
    @patch(f"{COMMAND_MODULE}.subprocess")
    @patch(f"{COMMAND_MODULE}.timezone")
    def test_skips_monthly_backup_on_other_days(
        self, mock_timezone, mock_subprocess, mock_boto3
    ):
        from datetime import UTC, datetime

        mock_timezone.localtime.return_value = datetime(
            2026, 8, 15, 3, 0, 0, tzinfo=UTC
        )
        mock_subprocess.run.return_value = _fake_dump_result(b"dump")
        fake_client = MagicMock()
        fake_client.list_objects_v2.return_value = {"Contents": []}
        mock_boto3.client.return_value = fake_client

        call_command("backup_database")

        monthly_calls = [
            call
            for call in fake_client.put_object.call_args_list
            if "monthly" in call.kwargs["Key"]
        ]
        self.assertEqual(monthly_calls, [])

    @patch(f"{COMMAND_MODULE}.boto3")
    @patch(f"{COMMAND_MODULE}.subprocess")
    def test_retention_deletes_objects_beyond_keep_count(
        self, mock_subprocess, mock_boto3
    ):
        mock_subprocess.run.return_value = _fake_dump_result(b"dump")
        fake_client = MagicMock()
        # 32件の日次バックアップ（保持数30を2件超過）。
        contents = [
            {"Key": f"backups/daily/2026-08-{day:02d}.sql.gz"} for day in range(1, 33)
        ]
        fake_client.list_objects_v2.side_effect = lambda Bucket, Prefix: {
            "Contents": [c for c in contents if c["Key"].startswith(Prefix)]
        }
        mock_boto3.client.return_value = fake_client

        call_command("backup_database")

        deleted_keys = {
            call.kwargs["Key"] for call in fake_client.delete_object.call_args_list
        }
        # 日付降順で新しい30件を残すため、古い2件（01, 02）が削除対象。
        self.assertIn("backups/daily/2026-08-01.sql.gz", deleted_keys)
        self.assertIn("backups/daily/2026-08-02.sql.gz", deleted_keys)
        self.assertNotIn("backups/daily/2026-08-03.sql.gz", deleted_keys)

    @patch(f"{COMMAND_MODULE}.notify_admin")
    def test_missing_bucket_name_raises_and_notifies(self, mock_notify):
        with (
            override_settings(BACKUP_BUCKET_NAME=""),
            self.assertRaises(CommandError),
        ):
            call_command("backup_database")
        mock_notify.assert_called_once()

    @patch(f"{COMMAND_MODULE}.notify_admin")
    @patch(f"{COMMAND_MODULE}.subprocess")
    def test_mysqldump_failure_raises_and_notifies(self, mock_subprocess, mock_notify):
        mock_subprocess.run.side_effect = subprocess.CalledProcessError(1, "mysqldump")

        with self.assertRaises(CommandError):
            call_command("backup_database")
        mock_notify.assert_called_once()
