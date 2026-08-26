import gzip
import os
import subprocess

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from kakeibo.notifications import notify_admin

DAILY_PREFIX = "backups/daily/"
MONTHLY_PREFIX = "backups/monthly/"
DAILY_RETENTION = 30
MONTHLY_RETENTION = 12


class Command(BaseCommand):
    """要件6.4: DBを日次バックアップしOCI Object Storageへ保管する（基本設計書7.2節）。"""

    help = "mysqldumpによるDBバックアップを取得しOCI Object Storageへ保管する（日次CronJobから実行する）"

    def handle(self, *args, **options):
        try:
            self._run()
        except Exception as exc:
            notify_admin("バックアップが失敗しました", str(exc))
            raise CommandError(f"バックアップが失敗しました: {exc}") from exc

    def _run(self):
        if not settings.BACKUP_BUCKET_NAME:
            raise CommandError("BACKUP_BUCKET_NAMEが未設定です")

        now = timezone.localtime()
        compressed = gzip.compress(self._dump_database())
        client = self._build_client()

        daily_key = f"{DAILY_PREFIX}{now:%Y-%m-%d}.sql.gz"
        client.put_object(
            Bucket=settings.BACKUP_BUCKET_NAME, Key=daily_key, Body=compressed
        )
        self.stdout.write(
            self.style.SUCCESS(f"日次バックアップを保存しました: {daily_key}")
        )

        if now.day == 1:
            # 基本設計書7.2節: 月次12世代。月初の日次バックアップを月次分としても保管する。
            monthly_key = f"{MONTHLY_PREFIX}{now:%Y-%m}.sql.gz"
            client.put_object(
                Bucket=settings.BACKUP_BUCKET_NAME, Key=monthly_key, Body=compressed
            )
            self.stdout.write(
                self.style.SUCCESS(f"月次バックアップを保存しました: {monthly_key}")
            )

        self._apply_retention(client, DAILY_PREFIX, DAILY_RETENTION)
        self._apply_retention(client, MONTHLY_PREFIX, MONTHLY_RETENTION)

    def _dump_database(self) -> bytes:
        db = settings.DATABASES["default"]
        host = db.get("HOST", "")
        command = ["mysqldump", f"--user={db['USER']}"]
        if host.startswith("/"):
            command.append(f"--socket={host}")
        else:
            command.append(f"--host={host or '127.0.0.1'}")
            if db.get("PORT"):
                command.append(f"--port={db['PORT']}")
        command.append(db["NAME"])

        # パスワードはコマンドライン引数にせずMYSQL_PWD経由で渡す（プロセス一覧への露出を避ける）。
        env = {**os.environ, "MYSQL_PWD": db["PASSWORD"]}
        result = subprocess.run(command, env=env, capture_output=True, check=True)
        return result.stdout

    def _build_client(self):
        return boto3.client(
            "s3",
            endpoint_url=settings.BACKUP_S3_ENDPOINT_URL,
            aws_access_key_id=settings.BACKUP_S3_ACCESS_KEY,
            aws_secret_access_key=settings.BACKUP_S3_SECRET_KEY,
            region_name=settings.BACKUP_S3_REGION,
        )

    def _apply_retention(self, client, prefix, keep_count):
        response = client.list_objects_v2(
            Bucket=settings.BACKUP_BUCKET_NAME, Prefix=prefix
        )
        # オブジェクトキーに日付（YYYY-MM-DD/YYYY-MM）を含むため、キーの降順=新しい順になる。
        objects = sorted(
            response.get("Contents", []), key=lambda o: o["Key"], reverse=True
        )
        for obj in objects[keep_count:]:
            client.delete_object(Bucket=settings.BACKUP_BUCKET_NAME, Key=obj["Key"])
