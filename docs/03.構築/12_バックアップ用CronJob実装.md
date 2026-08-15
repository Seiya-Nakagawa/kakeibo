# 12 構築手順書 - バックアップ用CronJob実装

## 目次

- [1. 概要](#1-概要)
- [2. 前提条件](#2-前提条件)
- [3. 手順](#3-手順)
  - [3.1. OCI Object Storageバケットとアクセスキーを準備する](#31-oci-object-storageバケットとアクセスキーを準備する)
  - [3.2. 依存パッケージを追加する](#32-依存パッケージを追加する)
  - [3.3. 環境変数を設定する](#33-環境変数を設定する)
  - [3.4. 設定値を追加する](#34-設定値を追加する)
  - [3.5. Dockerfileにmysqldumpを追加する](#35-dockerfileにmysqldumpを追加する)
  - [3.6. 管理コマンドを実装する](#36-管理コマンドを実装する)
  - [3.7. 設計書に保管先の詳細を追記する](#37-設計書に保管先の詳細を追記する)
  - [3.8. テストを追加する](#38-テストを追加する)
  - [3.9. 動作確認](#39-動作確認)

## 1. 概要

対応Issue: [#28](https://github.com/Seiya-Nakagawa/kakeibo/issues/28)

`mysqldump`による日次バックアップを取得し、OCI Object Storageへ保管するバッチを実装する。
日次30世代・月次12世代の世代管理、成否の通知連携を行う。
対応する設計書: [基本設計書7.2節](../02.設計/基本設計書.md#72-バックアップ要件-64)

**注意**: OCI Object Storageへの認証方式として、OCI SDK固有の認証情報
（テナンシOCID・ユーザーOCID・APIキー等）を増やさずアクセスキー・シークレットキーの
2値のみで完結する[Amazon S3互換API](https://docs.oracle.com/ja-jp/iaas/Content/Object/Tasks/s3compatibleapi.htm)
（`boto3`）を採用した。設計書に採用理由を追記済み（3.7参照）。

## 2. 前提条件

- [11_資産残高画面実装.md](11_資産残高画面実装.md) の完了
- [08_通知機能実装.md](08_通知機能実装.md) の完了により`notify_admin`が利用可能であること

## 3. 手順

### 3.1. OCI Object Storageバケットとアクセスキーを準備する

1. OCIコンソールでバックアップ保管用のバケット（例: `kakeibo-backups`）を作成する
2. OCIコンソールの「ユーザー設定」→「Customer Secret Keys」でアクセスキー・
   シークレットキーを発行する（S3互換API用）
3. Object StorageのS3互換APIエンドポイント（`https://<namespace>.compat.objectstorage.<region>.oraclecloud.com`）
   を確認する

### 3.2. 依存パッケージを追加する

`webapp/pyproject.toml`の`dependencies`に`boto3>=1.40.0`を追加する。

```bash
cd webapp
uv sync
```

### 3.3. 環境変数を設定する

`webapp/.env.example`の末尾に以下を追記する。

```dotenv
# バックアップ保管先（OCI Object Storage、S3互換API、基本設計書7.2節）
BACKUP_S3_ENDPOINT_URL=change-me
BACKUP_S3_ACCESS_KEY=change-me
BACKUP_S3_SECRET_KEY=change-me
BACKUP_S3_REGION=change-me
BACKUP_BUCKET_NAME=change-me
```

`webapp/.env`に、3.1で準備した実際の値を設定する。

### 3.4. 設定値を追加する

`webapp/config/settings/base.py`に以下を追加する。

```python
# バックアップ（要件6.4、基本設計書7.2節）: OCI Object StorageへS3互換API（boto3）で保管する。
BACKUP_S3_ENDPOINT_URL = env("BACKUP_S3_ENDPOINT_URL", default="")
BACKUP_S3_ACCESS_KEY = env("BACKUP_S3_ACCESS_KEY", default="")
BACKUP_S3_SECRET_KEY = env("BACKUP_S3_SECRET_KEY", default="")
BACKUP_S3_REGION = env("BACKUP_S3_REGION", default="")
BACKUP_BUCKET_NAME = env("BACKUP_BUCKET_NAME", default="")
```

### 3.5. Dockerfileにmysqldumpを追加する

`mysqldump`はPythonパッケージ（`mysqlclient`）に含まれないCLIツールのため、
`webapp/Dockerfile`のruntimeステージに`default-mysql-client`パッケージを追加する。

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmariadb3 \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser
```

### 3.6. 管理コマンドを実装する

`webapp/kakeibo/management/commands/backup_database.py`を新規作成する。

```python
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
        client.put_object(Bucket=settings.BACKUP_BUCKET_NAME, Key=daily_key, Body=compressed)
        self.stdout.write(self.style.SUCCESS(f"日次バックアップを保存しました: {daily_key}"))

        if now.day == 1:
            # 基本設計書7.2節: 月次12世代。月初の日次バックアップを月次分としても保管する。
            monthly_key = f"{MONTHLY_PREFIX}{now:%Y-%m}.sql.gz"
            client.put_object(Bucket=settings.BACKUP_BUCKET_NAME, Key=monthly_key, Body=compressed)
            self.stdout.write(self.style.SUCCESS(f"月次バックアップを保存しました: {monthly_key}"))

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
        response = client.list_objects_v2(Bucket=settings.BACKUP_BUCKET_NAME, Prefix=prefix)
        # オブジェクトキーに日付（YYYY-MM-DD/YYYY-MM）を含むため、キーの降順=新しい順になる。
        objects = sorted(response.get("Contents", []), key=lambda o: o["Key"], reverse=True)
        for obj in objects[keep_count:]:
            client.delete_object(Bucket=settings.BACKUP_BUCKET_NAME, Key=obj["Key"])
```

### 3.7. 設計書に保管先の詳細を追記する

[基本設計書7.2節](../02.設計/基本設計書.md#72-バックアップ要件-64)の表に、保管先が
S3互換APIであること、世代管理のプレフィックス構成（`backups/daily/`・
`backups/monthly/`、オブジェクトキーの日付降順で保持し超過分を削除）を追記する。

### 3.8. テストを追加する

`webapp/kakeibo/tests/test_backup_database.py`に、`subprocess.run`・`boto3.client`を
モック化した以下のテストを追加する。

- 日次バックアップがgzip圧縮されて正しいキーでアップロードされること
- 月初（`day == 1`）のみ月次バックアップも保存されること、それ以外の日はしないこと
- 世代管理で保持数を超えた古いオブジェクトが削除されること
- `BACKUP_BUCKET_NAME`未設定時に`CommandError`となり通知されること
- `mysqldump`失敗時に`CommandError`となり通知されること

### 3.9. 動作確認

```bash
cd webapp
uv run python manage.py test kakeibo
uvx ruff check .
uvx ruff format --check .
```

実際のOCI Object Storageへのアップロード確認は、3.1で発行したアクセスキーを
ローカルの`.env`に設定した状態で`uv run python manage.py backup_database`を実行し、
OCIコンソールでオブジェクトが保存されていることを確認する。
