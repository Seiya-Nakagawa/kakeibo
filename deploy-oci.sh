#!/bin/bash
set -euo pipefail

SSH_HOST="217.142.230.83"
SSH_USER="seiya"
SSH_KEY="$HOME/.ssh/id_rsa"
SSH_TARGET="${SSH_USER}@${SSH_HOST}"
NAMESPACE="app-prod"

echo "=================================================="
echo "🚀 [1/5] Dockerイメージをlinux/arm64向けにビルドしています..."
echo "=================================================="
docker build --platform linux/arm64 --provenance=false -t kakeibo:latest ./webapp

echo "=================================================="
echo "📦 [2/5] イメージをOCIホストのcontainerdへ転送・ロード中..."
echo "=================================================="
docker save kakeibo:latest | gzip | ssh -i "$SSH_KEY" "$SSH_TARGET" "sudo nerdctl -n k8s.io load"

echo "=================================================="
echo "📄 [3/5] Kubernetesマニフェストを適用しています..."
echo "=================================================="
# configmap, vault-sync, web, cronjob を適用する。Namespace・Ingress・TLS証明書は
# 全サービス共有のため基盤側（infra-oci）で管理しており、ここでは適用しない。
ssh -i "$SSH_KEY" "$SSH_TARGET" "mkdir -p /tmp/kakeibo-k8s"
scp -i "$SSH_KEY" k8s/configmap.yaml k8s/vault-sync.yaml k8s/web.yaml k8s/cronjob-mail-import.yaml "${SSH_TARGET}:/tmp/kakeibo-k8s/"
ssh -i "$SSH_KEY" "$SSH_TARGET" "kubectl apply -f /tmp/kakeibo-k8s/"

echo "=================================================="
echo "⏳ [4/5] Web Podのロールアウト完了を待機しています..."
echo "=================================================="
ssh -i "$SSH_KEY" "$SSH_TARGET" "kubectl rollout restart deployment/kakeibo-web -n ${NAMESPACE} || true"
ssh -i "$SSH_KEY" "$SSH_TARGET" "kubectl rollout status deployment/kakeibo-web -n ${NAMESPACE} --timeout=120s"

echo "=================================================="
echo "🔄 [5/5] Djangoマイグレーションを実行しています..."
echo "=================================================="
POD_NAME=$(ssh -i "$SSH_KEY" "$SSH_TARGET" "kubectl get pods -n ${NAMESPACE} -l app=kakeibo-web -o jsonpath='{.items[0].metadata.name}'")
echo "Target Pod: $POD_NAME"
ssh -i "$SSH_KEY" "$SSH_TARGET" "kubectl exec -n ${NAMESPACE} $POD_NAME -c web -- python manage.py migrate"

echo "=================================================="
echo "🎉 デプロイが完了しました！"
echo "=================================================="
ssh -i "$SSH_KEY" "$SSH_TARGET" "kubectl get pods,ingress,certificate -n ${NAMESPACE}"

