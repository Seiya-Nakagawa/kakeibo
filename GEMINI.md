# GEMINI.md

このファイルは、本リポジトリで作業する AI アシスタントへのガイダンスです。

## 1. 基本方針

- 文字コード: **UTF-8**
- 改行コード: **LF**
- 言語: 日本語を基本とする。
- **AI の応答は日本語で行う。**

## 2. 開発ワークフロー (GAS)

1. **GAS への反映**: `clasp push -f` を実行して GAS 環境へ反映する。
2. **デプロイ (本番反映)**:
   - テスト用に新しいバージョンを作成しない。
   - 以下の固定デプロイIDに対して上書き更新を行う。
   - `clasp deploy -i AKfycbwJkGi-ZjBbujrOGC5lajEsW_bEzO8vfhhqtZwaA_ltEMRkQcz_X6Qx46fzimgel_sfVg -d "変更内容の説明"`
3. **動作確認**: ユーザーに対して以下の本番URLでの動作確認を依頼する。
   - URL: <https://script.google.com/macros/s/AKfycbwJkGi-ZjBbujrOGC5lajEsW_bEzO8vfhhqtZwaA_ltEMRkQcz_X6Qx46fzimgel_sfVg/exec>
4. **Git への反映**: ユーザーから動作確認完了（OK）の連絡を受けた後にのみ、`git commit`、`git push` を行う。

## 3. 家族共有・複数ユーザー利用時の注意点

- **実行ユーザー**: `executeAs: "USER_DEPLOYING"` (自分) に設定すること。これにより、アクセスするユーザーに個別の権限承認を求めないようにする。
- **アクセス権限**: `access: "ANYONE_ANONYMOUS"` (全員) に設定することで、ログイン不要でアクセス可能にする。
- **承認手順**: スコープ変更を伴うデプロイ後は、必ず開発者アカウントで一度URLを開き、承認フロー（「詳細」→「移動」）を完了させること。これを怠ると、他のユーザーがアクセスした際に警告が表示される。

## 4. 機密情報の取り扱い

- API キーなどの機密情報は、コード内に直接記述せず、スクリプトプロパティを使用する。
