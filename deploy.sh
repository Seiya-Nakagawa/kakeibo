#!/bin/bash
set -e

# claspのログイン状態をチェック
echo "🔑 claspの認証状態をチェックしています..."
if ! npx clasp status >/dev/null 2>&1; then
  echo "⚠️  エラー: claspのログインセッションが切れているか、無効です。"
  echo "👉 以下のコマンドを実行して再ログインしてください："
  echo "   npx clasp login"
  exit 1
fi

echo "✅ 認証OK"

# コードのプッシュ
echo "🚀 GASにコードをプッシュしています..."
npx clasp push -f

# デプロイの更新
echo "📦 本番環境へデプロイしています..."
DEPLOY_ID="AKfycbwJkGi-ZjBbujrOGC5lajEsW_bEzO8vfhhqtZwaA_ltEMRkQcz_X6Qx46fzimgel_sfVg"
npx clasp deploy -i "$DEPLOY_ID" -d "自動デプロイ: $(date +'%Y-%m-%d %H:%M:%S')"

echo "🎉 デプロイが完了しました！"
echo "--------------------------------------------------"
echo "⚠️  【重要】スコープ（権限）の変更があった場合："
echo "1. 他のユーザーがアクセスした際にエラーが出るのを防ぐため、"
echo "   以下の本番URLをご自身の開発者アカウントで一度開き、承認フローを完了させてください："
URL="https://script.google.com/macros/s/$DEPLOY_ID/exec"
echo "   👉 $URL"
echo "2. 時間トリガー(runAutoImport)が 'Authorization is required...' でエラーになるのを防ぐため、"
echo "   Google Apps Scriptエディタを開き、関数(runAutoImportなど)を一度手動実行して、"
echo "   承認ダイアログ（権限の確認）を完了させてください。"
echo "--------------------------------------------------"

echo "🌐 動作確認とOAuth承認のため、本番URLをブラウザで開いています..."
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL"
elif command -v open >/dev/null 2>&1; then
  open "$URL"
else
  echo "👉 手動でURLを開いて確認してください: $URL"
fi

