#!/bin/bash
set -euo pipefail

SSH_HOST="217.142.230.83"
SSH_USER="seiya"
SSH_KEY="$HOME/.ssh/id_rsa"
SSH_TARGET="${SSH_USER}@${SSH_HOST}"

ENV_FILE="${1:-webapp/.env.production}"

if [ ! -f "$ENV_FILE" ]; then
    echo "Usage: $0 <path-to-.env.production>"
    echo "Error: Environment file '$ENV_FILE' not found."
    exit 1
fi

echo "Creating namespace 'kakeibo' if not exists..."
ssh -i "$SSH_KEY" "$SSH_TARGET" "kubectl create namespace kakeibo --dry-run=client -o yaml | kubectl apply -f -"

echo "Applying secrets from '$ENV_FILE'..."
scp -i "$SSH_KEY" "$ENV_FILE" "${SSH_TARGET}:/tmp/kakeibo.env"
ssh -i "$SSH_KEY" "$SSH_TARGET" "kubectl create secret generic kakeibo-secrets -n kakeibo --from-env-file=/tmp/kakeibo.env --dry-run=client -o yaml | kubectl apply -f - && rm -f /tmp/kakeibo.env"

echo "✅ Secret 'kakeibo-secrets' successfully updated in namespace 'kakeibo'."
