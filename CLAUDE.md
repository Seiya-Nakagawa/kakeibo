# kakeibo プロジェクト規約

## コード変更とドキュメントの同期

コードを変更する際は、必ず `docs/` 以下のドキュメントも同時に更新すること。

- 仕様変更（シート構成、フィールド追加、カテゴリ変更など） → `docs/DESIGN.md` を更新
- 機能要件の変更 → `docs/REQUIREMENTS.md` を更新

## デプロイ

GAS へのデプロイは gas-deploy スキルを使うこと。

```bash
clasp push
```

## ラベル

Issue・PR は `enhancement`（機能追加）または `bug`（バグ修正）ラベルを付ける。
