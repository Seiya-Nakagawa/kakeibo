# GEMINI.md

このファイルは、本リポジトリ固有の事情を記録したものです。

基本方針（文字コード、言語）、Git 運用、Markdown 記法などの共通規約はグローバル規約
（`~/.claude/CLAUDE.md`、`~/.gemini/GEMINI.md`、`~/.claude/rules/`）を参照してください。
**本ファイルに共通規約を重複定義しないこと。**

## 1. デプロイ情報 (GAS)

デプロイ手順そのものはグローバル規約の `~/.claude/rules/gas-deploy-flow.md` に従います。
本リポジトリ固有の値は以下のとおりです。

- **固定デプロイ ID**: `AKfycbwJkGi-ZjBbujrOGC5lajEsW_bEzO8vfhhqtZwaA_ltEMRkQcz_X6Qx46fzimgel_sfVg`
  - テスト用に新しいバージョンを作成せず、この ID に対して上書き更新する。
- **本番 URL**: <https://script.google.com/macros/s/AKfycbwJkGi-ZjBbujrOGC5lajEsW_bEzO8vfhhqtZwaA_ltEMRkQcz_X6Qx46fzimgel_sfVg/exec>
  - デプロイ後、この URL でユーザーに動作確認を依頼する。

## 2. 家族共有・複数ユーザー利用時の注意点

- **実行ユーザー**: `executeAs: "USER_DEPLOYING"` (自分) に設定すること。これにより、アクセスするユーザーに個別の権限承認を求めないようにする。
- **アクセス権限**: `access: "ANYONE_ANONYMOUS"` (全員) に設定することで、ログイン不要でアクセス可能にする。
- **承認手順**: スコープ変更を伴うデプロイ後は、必ず開発者アカウントで一度URLを開き、承認フロー（「詳細」→「移動」）を完了させること。これを怠ると、他のユーザーがアクセスした際に警告が表示される。

## 3. 機密情報の取り扱い

- API キーなどの機密情報は、コード内に直接記述せず、スクリプトプロパティを使用する。

## 4. 恒久対策・トラブルシューティング

- **ログイン状態とデプロイの自動確認**:
  - デプロイの失敗（claspのセッション切れ）やデプロイ後の警告忘れを防ぐため、常にルートの `./deploy.sh` スクリプトを使用してプッシュ・デプロイを行うこと。
  - このスクリプトは `clasp` のログインが切れている場合に処理を中断し、再ログインを促します。
- **「アクセス権が必要です」と表示された場合や時間トリガー（runAutoImport）が「Authorization is required...」で失敗する場合**:
  - Web Appのアクセス設定（`access: "ANYONE_ANONYMOUS"`）や必要なアクセス権限（Scopes）に変更があった場合、Googleが承認を求めます。
  - **Web Appの承認方法**: 開発者のGoogleアカウントで [本番URL](https://script.google.com/macros/s/AKfycbwJkGi-ZjBbujrOGC5lajEsW_bEzO8vfhhqtZwaA_ltEMRkQcz_X6Qx46fzimgel_sfVg/exec) を一度ブラウザで開き、承認フロー（詳細 ＞ 移動）を完了させてください。
  - **時間トリガーの承認方法**: スコープ変更などにより、時間トリガーの動作に必要な権限が不足している場合に発生します。以下の手順で再承認を行ってください。
    1. Google Apps Scriptのウェブエディタを開きます。
    2. 関数一覧から `runAutoImport` （または任意の関数）を選択し、**手動で「実行」ボタンをクリック**します。
    3. 「承認が必要です」というダイアログが表示されるので、「権限を確認」をクリックして承認フロー（詳細 ＞ 移動 ＞ 許可）を完了させてください。
    4. これでもエラーが解消しない場合は、GAS左側メニューの「トリガー」（時計マーク）から、該当のトリガーを一度削除して再作成してください。
