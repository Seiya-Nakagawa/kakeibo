# 01 構築手順書 - Djangoプロジェクトの初期構築

## 目次

- [1. 概要](#1-概要)
- [2. 前提条件](#2-前提条件)
- [3. 手順](#3-手順)
  - [3.1. uv 環境の初期化](#31-uv-環境の初期化)
  - [3.2. Django プロジェクト本体の作成](#32-django-プロジェクト本体の作成)
  - [3.3. 設定ファイルの分割](#33-設定ファイルの分割)
  - [3.4. 本番用パッケージ・コンテナイメージの追加](#34-本番用パッケージコンテナイメージの追加)

## 1. 概要

対応Issue: [#18](https://github.com/Seiya-Nakagawa/kakeibo/issues/18)

Django プロジェクトの雛形を作成する。Python 3.14 / Django 5.2.8 以降のプロジェクトを
作成し、開発/本番の設定分割、環境変数によるシークレット管理、コンテナイメージ化
（Dockerfile）、ローカル開発環境（docker compose）を整備する。
対応する設計書: [基本設計書 2章](../02.設計/基本設計書.md#2-技術スタック)

## 2. 前提条件

- Python 3.14、uv がインストール済みであること
- リポジトリ直下に `webapp/` ディレクトリを作成する（Django プロジェクトの配置場所）

## 3. 手順

### 3.1. uv 環境の初期化

```bash
cd webapp
uv init --python 3.14
uv add "django>=5.2.8,<5.3" django-environ mysqlclient
```

- Python 3.14 を指定して `pyproject.toml` を持つ uv プロジェクトを初期化する
- Django / django-environ / mysqlclient を依存関係として追加する

`.gitignore` に Python/uv 関連の除外設定を追加する。

```gitignore
# Python / uv
.venv/
__pycache__/
*.pyc
db.sqlite3
```

### 3.2. Django プロジェクト本体の作成

`uv init` が生成した `main.py` を削除し、`config` という名前で Django プロジェクトを作成する。

```bash
rm main.py
uv run django-admin startproject config .
```

- `config` という名前の Django プロジェクトをカレントディレクトリ（`webapp/`）に作成する

### 3.3. 設定ファイルの分割

`config/settings.py` を `config/settings/` ディレクトリに分割する。

- `config/settings/base.py`: 共通設定（`INSTALLED_APPS`、`MIDDLEWARE`、`TEMPLATES`、
  `TIME_ZONE = 'Asia/Tokyo'` 等）。`SECRET_KEY` は `django-environ` 経由で `.env` から読む
- `config/settings/development.py`: `DEBUG = True`。MySQL へは TCP 接続
  （`DB_HOST` / `DB_PORT`、既定値 `127.0.0.1` / `3306`）
- `config/settings/production.py`: `DEBUG = False`。MySQL へは Unix ソケット接続
  （`DB_SOCKET_PATH`、既定値 `/var/run/mysqld/mysqld.sock`）。
  接続方式の採用理由は [基本設計書 4.1.1](../02.設計/基本設計書.md#411-pod-から-mysql-への接続方式) を参照

`webapp/manage.py` の既定 `DJANGO_SETTINGS_MODULE` を `config.settings.development` にする。

`webapp/.env.example` を作成し、`SECRET_KEY` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` /
`DB_ROOT_PASSWORD` 等、必要な環境変数のテンプレートを記載する。

### 3.4. 本番用パッケージ・コンテナイメージの追加

```bash
uv add gunicorn
```

- 本番用 WSGI サーバー gunicorn を依存関係に追加する

`webapp/Dockerfile` を multi-stage 構成で作成する。

- `builder` ステージ: `python:3.14-slim` に `mysqlclient` のビルドに必要な
  `default-libmysqlclient-dev` 等を導入し、`uv sync --locked` で依存関係を解決する
- `runtime` ステージ: 実行に必要な `libmariadb3` のみを導入し、非 root ユーザー
  （`appuser`）で `gunicorn` を起動する

`webapp/docker-compose.yml` を作成し、`mysql:8.0`（文字コード `utf8mb4` /
照合順序 `utf8mb4_0900_ai_ci` を起動オプションで指定）と Django アプリ（`web`）の
2 サービスでローカル開発環境を構成する。
