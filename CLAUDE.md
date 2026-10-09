# CLAUDE.md

このファイルは、本リポジトリ固有の事情を記録したものです。

基本方針・機密情報の取り扱い・Git 運用・コーディング規約・Markdown 記法などの共通規約は
グローバル規約（`~/.claude/`）に従います。
**本ファイルに共通規約を重複定義しないこと。**

## CI/CD（GitHub Actions）

- `.github/workflows/ci.yml`: Pull Request 作成時に `webapp/` の `ruff`・Django テストを実行する
- `.github/workflows/deploy.yml`: `main` マージ後、`scripts/deploy_via_bastion.sh` 経由で
  `deploy-oci.sh` を実行し本番環境（OCI ホストの `app-prod`）へ自動デプロイする
- OCI Bastion の Managed SSH Session を使い、セキュリティ・リストを変更せずに GitHub Actions から
  OCI ホストへ到達する（詳細は [基本設計書 7.4.1節](docs/02.設計/基本設計書.md#741-cicd-パイプライン)）
- GitHub Secrets: `BASTION_OCI_PRIVATE_KEY`（秘密鍵のみ）。IAM ユーザーは Portfolio・infra-oci と共用
- 作業端末からの `deploy-oci.sh` 直接実行は、障害調査等の一時的な用途にのみ使う

## GAS（`app/`）固有の事情

デプロイ手順そのものはグローバル規約（`~/.claude/rules/gas-deploy-flow.md`）に従う。

- **固定デプロイ ID**: `AKfycbwJkGi-ZjBbujrOGC5lajEsW_bEzO8vfhhqtZwaA_ltEMRkQcz_X6Qx46fzimgel_sfVg`
  （テスト用に新しいバージョンを作成せず、この ID に対して上書き更新する）
- **本番 URL**: <https://script.google.com/macros/s/AKfycbwJkGi-ZjBbujrOGC5lajEsW_bEzO8vfhhqtZwaA_ltEMRkQcz_X6Qx46fzimgel_sfVg/exec>
  （デプロイ後、この URL でユーザーに動作確認を依頼する）
- **デプロイは `./deploy.sh` を使う**: `clasp` のログイン切れを検出して中断し、再ログインを促す
- **公開設定**: `executeAs: "USER_DEPLOYING"`、`access: "ANYONE_ANONYMOUS"`。家族など複数ユーザーが
  個別の権限承認なし・ログイン不要でアクセスできるようにするため
- **スコープ変更を伴うデプロイ後の承認**: 開発者アカウントで本番 URL を一度開き、承認フロー
  （「詳細」→「移動」）を完了させる。怠ると他のユーザーに警告が表示される
- **時間トリガー（`runAutoImport`）が「Authorization is required...」で失敗する場合**:
  1. GAS のウェブエディタで `runAutoImport` を手動実行し、「権限を確認」から承認フロー（詳細 → 移動 → 許可）を完了させる
  2. 解消しない場合は「トリガー」から該当トリガーを削除して再作成する
