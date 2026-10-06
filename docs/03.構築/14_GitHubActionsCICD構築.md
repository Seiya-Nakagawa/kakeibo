# 14 構築手順書 - GitHub Actions CI/CD の構築

## 目次

- [1. 概要](#1-概要)
- [2. 前提条件](#2-前提条件)
- [3. 手順](#3-手順)
  - [3.1. GitHub Secretsへの登録](#31-github-secretsへの登録)
  - [3.2. 動作確認](#32-動作確認)

## 1. 概要

対応Issue: [#95](https://github.com/Seiya-Nakagawa/kakeibo/issues/95)

本番デプロイ（`deploy-oci.sh`）の実行主体をローカルから GitHub Actions へ移行する。
Pull Request 作成時にテスト・Lint（CI）、`main` マージ後に本番デプロイ（CD）を自動実行する。
CD から OCI ホストへの接続は、セキュリティ・リストを変更せず OCI Bastion の Managed SSH Session
経由で行う（設計は [基本設計書 7.4.1節](../02.設計/基本設計書.md#741-cicd-パイプライン) を参照）。

Bastion セッション作成専用の最小権限 IAM ユーザー・グループ・ポリシーは infra-oci リポジトリの
Terraform で作成済みであり、infra-oci の Ansible CI/CD および Portfolio リポジトリと同一の
IAM ユーザーを本リポジトリでも共用する。IAM ユーザー自体の新規作成は不要。

## 2. 前提条件

- infra-oci リポジトリで Bastion と CI/CD 専用 IAM グループ・ポリシー
  （`manage bastion-session` のみを許可）が適用済みであること
- infra-oci セットアップ時にダウンロードした CI/CD 専用 IAM ユーザー
  （`github-actions-ansible-bastion`）の秘密鍵ファイルを保持していること
  （ユーザー OCID・フィンガープリントは秘密情報ではないため `scripts/deploy_via_bastion.sh` に
  直接定義済みで、登録作業は不要）
- 本リポジトリの管理者権限を持つこと（GitHub Secrets の登録に必要）

## 3. 手順

### 3.1. GitHub Secretsへの登録

GitHub の個人アカウント配下では Secrets をリポジトリ単位でしか登録できないため、
共通スクリプトで登録する。対話入力は発生しない。

```bash
~/.claude/scripts/gh_secret_set_oci_bastion.sh Seiya-Nakagawa/kakeibo /path/to/oci_api_key.pem
```

- `BASTION_OCI_PRIVATE_KEY`（秘密鍵ファイルの内容全体）のみを登録する。IAM ユーザーを共用するため、
  新しい API キーの発行は不要
- 秘密鍵ファイルの中身をチャットへ貼り付けない

### 3.2. 動作確認

1. `webapp/` 配下に差分を含む Pull Request を作成し、`CI` ワークフローの `test` ジョブ
   （`ruff`・Django テスト）が成功することを確認する
2. `main` へマージし、`Deploy` ワークフローが成功することを確認する
3. 本番の家計簿サイトが正常に表示されることを確認する
