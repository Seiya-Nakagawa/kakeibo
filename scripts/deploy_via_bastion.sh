#!/bin/bash

# OCI Bastion (Managed SSH Session) 経由で deploy-oci.sh を実行するラッパー。
# GitHub Actions から、セキュリティ・リストを変更せずに本番デプロイを行うために使う。
# OCI CLI の認証情報のうち、秘密鍵（OCI_CLI_KEY_CONTENT）のみ GitHub Secrets
# （BASTION_OCI_PRIVATE_KEY）から渡される前提とする。ユーザー OCID・フィンガープリントは
# 秘密情報ではないため下記に直接定義する。infra-oci リポジトリの
# scripts/run_ansible_bastion.sh と同じ方式。

set -euo pipefail

# OCI ホストは infra-oci リポジトリが管理する。値は infra-oci の `terraform output` を正とする。
BASTION_ID="ocid1.bastion.oc1.ap-osaka-1.amaaaaaapsxkv4qayqouh3tccmcoplq4oak4vx5ml5w7tg65fztbcvt7v3ha"
INSTANCE_OCID="ocid1.instance.oc1.ap-osaka-1.anvwsljrpsxkv4qcyn32rjh7y7gbldnjfzrm757fznhkvc7vt3cznawk5csa"
INSTANCE_PRIVATE_IP="10.0.1.60"
OS_USERNAME="seiya"
OCI_REGION="ap-osaka-1"
OCI_TENANCY_OCID="ocid1.tenancy.oc1..aaaaaaaacg5alpzvgeigrdm2zyjqnczctg7eqvl5bhqyaddfc64bhewtrciq"
BASTION_SESSION_TTL="${BASTION_SESSION_TTL:-1800}"

# Bastion セッション作成専用の最小権限 IAM ユーザー（github-actions-ansible-bastion）。
# OCID・フィンガープリントは秘密情報ではないため直接定義する（秘密鍵のみ Secrets 経由）。
export OCI_CLI_USER="ocid1.user.oc1..aaaaaaaaajzmsgey3q5hwfofdbxu23hxgiulbizuww4to6pbu5csvzv2fppa"
export OCI_CLI_FINGERPRINT="19:d9:03:da:3f:59:d1:e8:79:2d:91:08:7b:f0:d6:92"
export OCI_CLI_REGION="$OCI_REGION"
export OCI_CLI_TENANCY="$OCI_TENANCY_OCID"

for cmd in oci ssh-keygen ssh docker; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "Error: $cmd is not installed." >&2
        exit 1
    fi
done

SESSION_DIR=$(mktemp -d)
cleanup() {
    if [ -n "${SESSION_ID:-}" ]; then
        echo "=== セッションを削除中... (Session ID: $SESSION_ID) ==="
        oci bastion session delete --session-id "$SESSION_ID" --force > /dev/null 2>&1 || true
    fi
    rm -rf "$SESSION_DIR"
}
trap cleanup EXIT

ssh-keygen -t ed25519 -N "" -f "$SESSION_DIR/id_ed25519" -q

echo "=== [1/2] OCI Bastion の Managed SSH Session を作成中... ==="
SESSION_ID=$(oci bastion session create-managed-ssh \
    --bastion-id "$BASTION_ID" \
    --target-resource-id "$INSTANCE_OCID" \
    --target-os-username "$OS_USERNAME" \
    --target-private-ip "$INSTANCE_PRIVATE_IP" \
    --ssh-public-key-file "$SESSION_DIR/id_ed25519.pub" \
    --session-ttl "$BASTION_SESSION_TTL" \
    --display-name "gha-deploy-$(date +%s)" \
    --wait-for-state SUCCEEDED --wait-for-state FAILED \
    --query 'data.resources[0].identifier' --raw-output)

if [ -z "$SESSION_ID" ]; then
    echo "Error: Bastion セッションの作成に失敗しました。" >&2
    exit 1
fi
echo "  Session ID: $SESSION_ID"

BASTION_HOST="host.bastion.${OCI_REGION}.oci.oraclecloud.com"
PROXY_COMMAND="ssh -i $SESSION_DIR/id_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -W %h:%p -p 22 ${SESSION_ID}@${BASTION_HOST}"

# ProxyCommandを含む値をssh -oへシェル経由で渡すと壊れやすいため、ssh_config ファイル経由で渡す
SSH_CONFIG_FILE="$SESSION_DIR/ssh_config"
cat > "$SSH_CONFIG_FILE" <<EOF
Host ${INSTANCE_PRIVATE_IP}
    ProxyCommand ${PROXY_COMMAND}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
EOF

echo "=== [2/2] Bastionトンネル経由でdeploy-oci.shを実行します... ==="
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SSH_HOST="$INSTANCE_PRIVATE_IP" \
SSH_USER="$OS_USERNAME" \
SSH_KEY="$SESSION_DIR/id_ed25519" \
SSH_CONFIG_FILE="$SSH_CONFIG_FILE" \
"$SCRIPT_DIR/../deploy-oci.sh"
