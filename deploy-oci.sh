#!/bin/bash
set -euo pipefail

# 接続先は環境変数で上書きできる。GitHub Actions からは scripts/deploy_via_bastion.sh が
# OCI Bastion の Managed SSH Session（プライベート IP・一時鍵・SSH_CONFIG_FILE）を渡して呼び出す。
SSH_HOST="${SSH_HOST:-217.142.230.83}"
SSH_USER="${SSH_USER:-seiya}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"
SSH_TARGET="${SSH_USER}@${SSH_HOST}"
NAMESPACE="app-prod"

SSH_OPTS=()
if [ -n "${SSH_CONFIG_FILE:-}" ]; then
    SSH_OPTS+=(-F "$SSH_CONFIG_FILE")
fi

remote_ssh() {
    ssh -i "$SSH_KEY" "${SSH_OPTS[@]}" "$SSH_TARGET" "$@"
}

remote_scp() {
    scp -i "$SSH_KEY" "${SSH_OPTS[@]}" "$@"
}

echo "=================================================="
echo "🚀 [1/5] Dockerイメージをlinux/arm64向けにビルドしています..."
echo "=================================================="
docker build --platform linux/arm64 --provenance=false -t kakeibo:latest ./webapp

echo "=================================================="
echo "📦 [2/5] イメージをOCIホストのcontainerdへ転送・ロード中..."
echo "=================================================="
docker save kakeibo:latest | gzip | remote_ssh "sudo nerdctl -n k8s.io load"

echo "=================================================="
echo "📄 [3/5] Kubernetesマニフェストを適用しています..."
echo "=================================================="
# configmap, vault-sync, web, cronjob を適用する。Namespace・Ingress・TLS証明書は
# 全サービス共有のため基盤側（infra-oci）で管理しており、ここでは適用しない。
# 過去のデプロイで置かれた削除済みマニフェストを適用しないよう、転送先を毎回作り直す
remote_ssh "rm -rf /tmp/kakeibo-k8s && mkdir -p /tmp/kakeibo-k8s"
remote_scp k8s/configmap.yaml k8s/vault-sync.yaml k8s/web.yaml k8s/cronjob-mail-import.yaml "${SSH_TARGET}:/tmp/kakeibo-k8s/"
remote_ssh "kubectl apply -f /tmp/kakeibo-k8s/"

echo "=================================================="
echo "⏳ [4/5] Web Podのロールアウト完了を待機しています..."
echo "=================================================="
remote_ssh "kubectl rollout restart deployment/kakeibo-web -n ${NAMESPACE} || true"
remote_ssh "kubectl rollout status deployment/kakeibo-web -n ${NAMESPACE} --timeout=120s"

echo "=================================================="
echo "🔄 [5/5] Djangoマイグレーションを実行しています..."
echo "=================================================="
# ロールアウト直後は終了済みの古い Pod が残るため、Running の Pod に限定し、
# 複数該当する場合は作成日時が最新の Pod を選ぶ
POD_NAME=$(remote_ssh "kubectl get pods -n ${NAMESPACE} -l app=kakeibo-web --field-selector=status.phase=Running --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}'")
if [ -z "$POD_NAME" ]; then
    echo "Running 状態の kakeibo-web Pod が見つかりません。" >&2
    exit 1
fi
echo "Target Pod: $POD_NAME"
remote_ssh "kubectl exec -n ${NAMESPACE} $POD_NAME -c web -- python manage.py migrate"

echo "=================================================="
echo "🎉 デプロイが完了しました！"
echo "=================================================="
remote_ssh "kubectl get pods,ingress,certificate -n ${NAMESPACE}"

