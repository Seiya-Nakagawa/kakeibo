# kakeibo プロジェクト規約

グローバルの CLAUDE.md およびプロジェクト内の `GEMINI.md` を参照すること。

## CI/CD（GitHub Actions）

- `.github/workflows/ci.yml`: Pull Request 作成時に `webapp/` の `ruff`・Django テストを実行する
- `.github/workflows/deploy.yml`: `main` マージ後、`scripts/deploy_via_bastion.sh` 経由で
  `deploy-oci.sh` を実行し本番環境（OCI ホストの `app-prod`）へ自動デプロイする
- OCI Bastion の Managed SSH Session を使い、セキュリティ・リストを変更せずに GitHub Actions から
  OCI ホストへ到達する（詳細は [基本設計書 7.4.1節](docs/02.設計/基本設計書.md#741-cicd-パイプライン)）
- GitHub Secrets: `BASTION_OCI_PRIVATE_KEY`（秘密鍵のみ）。IAM ユーザーは Portfolio・infra-oci と共用
- 作業端末からの `deploy-oci.sh` 直接実行は、障害調査等の一時的な用途にのみ使う
