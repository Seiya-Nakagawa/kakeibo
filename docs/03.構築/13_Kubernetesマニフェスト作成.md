# 13 構築手順書 - Kubernetesマニフェスト作成

## 目次

- [1. 概要](#1-概要)
- [2. 前提条件](#2-前提条件)
- [3. 手順](#3-手順)
  - [3.1. FORCE_SCRIPT_NAMEを設定する](#31-force_script_nameを設定する)
  - [3.2. ConfigMapを作成する](#32-configmapを作成する)
  - [3.3. OCI Vaultへのシークレット登録・ExternalSecretを作成する](#33-oci-vaultへのシークレット登録externalsecretを作成する)
  - [3.4. Web Deployment・Serviceを作成する](#34-web-deploymentserviceを作成する)
  - [3.5. メール取込CronJobを作成する](#35-メール取込cronjobを作成する)
  - [3.6. マニフェストの構文を確認する](#36-マニフェストの構文を確認する)
  - [3.7. 共有Namespaceへ移行する](#37-共有namespaceへ移行する)

## 1. 概要

対応Issue: [#29](https://github.com/Seiya-Nakagawa/kakeibo/issues/29)

Web Pod・CronJob（メール取込）のKubernetesマニフェストを作成する。
対応する設計書: [基本設計書4.1.1節](../02.設計/基本設計書.md#411-pod-から-mysql-への接続方式)、
[1.1.1節](../02.設計/基本設計書.md#111-ドメインパス割り当て方針)、
[7.3節](../02.設計/基本設計書.md#73-セキュリティ要件-63)

**注意**: 以下は実クラスタでの検証（`kubectl apply`）ができていない。特に次の2点は
実際のクラスタ構成（`infra-oci-terraform`・`infra-oci-ansible`側の設定）に合わせて
要確認・要調整である。

- `k8s/web.yaml`・`k8s/cronjob-*.yaml`の`image`（コンテナイメージのレジストリ・タグ）

## 2. 前提条件

- `infra-oci-terraform`・`infra-oci-ansible`によりKubernetesクラスタ・
  ingress-nginx・cert-manager・External Secrets Operatorが構築済みであること
- 同じく`infra-oci`により、OCI Vaultと`ClusterSecretStore/oci-vault`
  （Instance Principal認証）が構築済みであること
- 全サービス共有の`app-prod`ネームスペース・共有Ingress・TLS証明書が`infra-oci`により
  構築済みであること（本リポジトリのマニフェストには含めない。共有Ingressは
  Service `kakeibo-web`（ポート80）を参照する）
- OCI CLIが利用でき、対象Vaultのシークレットを作成する権限があること

## 3. 手順

### 3.1. FORCE_SCRIPT_NAMEを設定する

`webapp/config/settings/production.py`に以下を追加する。

```python
# 基本設計書1.1.1節: /kakeibo配下で動作させるため、URL逆引き・リダイレクト先に
# プレフィックスを付与する。Ingress側は/kakeiboを除去してバックエンドへ転送する
# （基盤側の共有Ingressのrewrite-target）ため、Django側は付与のみを担う。
FORCE_SCRIPT_NAME = env("FORCE_SCRIPT_NAME", default="/kakeibo")
```

`webapp/.env.example`のコメントアウト済み本番専用設定に以下を追記する。

```dotenv
# FORCE_SCRIPT_NAME=/kakeibo
```

### 3.2. ConfigMapを作成する

`k8s/configmap.yaml`を新規作成する。機密情報を含まない設定値のみを保持する。

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kakeibo-config
  namespace: app-prod
data:
  ALLOWED_HOSTS: "technohonesty.com"
  FORCE_SCRIPT_NAME: "/kakeibo"
  DB_SOCKET_PATH: "/var/run/mysqld/mysqld.sock"
  SESSION_TIMEOUT_SECONDS: "1800"
```

### 3.3. OCI Vaultへのシークレット登録・ExternalSecretを作成する

OCI Vaultへ`kakeibo-*`のシークレットを登録し、External Secrets Operatorが`kakeibo-secrets`
（Kubernetes Secret）へ同期するよう`k8s/vault-sync.yaml`を作成する。
接続定義（`ClusterSecretStore/oci-vault`）は`infra-oci`側で構築済みのため、本リポジトリでは作成しない。

#### 3.3.1. Vaultの接続情報を取得する

`infra-oci`のTerraform出力（`oci_vault_id`・コンパートメントOCID・リージョン）を環境変数に設定する。

```bash
export VAULT_ID="{Vault OCID}"
export COMPARTMENT_ID="{コンパートメントOCID}"
export OCI_REGION="ap-osaka-1"
```

Vaultの管理エンドポイントを取得する。

```bash
oci kms management vault get --vault-id "$VAULT_ID" --region "$OCI_REGION" \
  --query 'data."management-endpoint"' --raw-output
```

取得した管理エンドポイントで、シークレットの暗号化に使う鍵（`infra-oci-app-db-key`）のOCIDを取得する。

```bash
export MANAGEMENT_ENDPOINT="{上記で取得した管理エンドポイント}"
oci kms management key list --compartment-id "$COMPARTMENT_ID" --endpoint "$MANAGEMENT_ENDPOINT" \
  --query 'data[*].{name:"display-name",id:id}' --output table
export KEY_ID="{infra-oci-app-db-keyのOCID}"
```

- 1つ目のコマンド: Vaultの管理エンドポイントを取得する
- 2つ目のコマンド: 管理エンドポイントを環境変数に設定し、Vault内の暗号化鍵の一覧を取得する

#### 3.3.2. シークレットを登録する

次の11件を登録する。Vaultのシークレット名は`kakeibo-`を接頭辞とする。

| Kubernetes Secretのキー | Vaultのシークレット名 |
| ----------------------- | --------------------- |
| `SECRET_KEY` | `kakeibo-secret-key` |
| `DB_NAME` | `kakeibo-db-name` |
| `DB_USER` | `kakeibo-db-user` |
| `DB_PASSWORD` | `kakeibo-db-password` |
| `GOOGLE_OAUTH_CLIENT_ID` | `kakeibo-google-oauth-client-id` |
| `GOOGLE_OAUTH_CLIENT_SECRET` | `kakeibo-google-oauth-client-secret` |
| `GMAIL_API_CLIENT_ID` | `kakeibo-gmail-api-client-id` |
| `GMAIL_API_CLIENT_SECRET` | `kakeibo-gmail-api-client-secret` |
| `GMAIL_API_REFRESH_TOKEN` | `kakeibo-gmail-api-refresh-token` |
| `NOTIFICATION_RECIPIENT_EMAIL` | `kakeibo-notification-recipient-email` |
| `MAIL_IMPORT_USER_EMAIL` | `kakeibo-mail-import-user-email` |

各シークレットを次のコマンドで登録する（表の全行について、名前と値を替えて繰り返す）。
値はBase64でエンコードして渡す。

```bash
oci vault secret create-base64 \
  --compartment-id "$COMPARTMENT_ID" --vault-id "$VAULT_ID" --key-id "$KEY_ID" \
  --region "$OCI_REGION" \
  --secret-name "kakeibo-secret-key" \
  --secret-content-content "$(printf '%s' "{登録する値}" | base64 -w0)"
```

- `--secret-name`: Vaultのシークレット名（上表の右列）
- `--secret-content-content`: 登録する値をBase64エンコードしたもの

登録直後は状態が`CREATING`となるため、全件が`ACTIVE`になったことを確認する。

```bash
oci vault secret list --compartment-id "$COMPARTMENT_ID" --vault-id "$VAULT_ID" \
  --region "$OCI_REGION" --all \
  --query 'data[*].{name:"secret-name",state:"lifecycle-state"}' --output table
```

- 各シークレットの名前と状態の一覧を取得する（値は取得しない）

#### 3.3.3. ExternalSecretを作成する

`k8s/vault-sync.yaml`を新規作成する。

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: kakeibo-secrets
  namespace: app-prod
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: oci-vault
    kind: ClusterSecretStore
  target:
    name: kakeibo-secrets
    creationPolicy: Owner
    deletionPolicy: Retain
  data:
    - secretKey: SECRET_KEY
      remoteRef:
        key: kakeibo-secret-key
    - secretKey: DB_NAME
      remoteRef:
        key: kakeibo-db-name
    - secretKey: DB_USER
      remoteRef:
        key: kakeibo-db-user
    - secretKey: DB_PASSWORD
      remoteRef:
        key: kakeibo-db-password
    - secretKey: GOOGLE_OAUTH_CLIENT_ID
      remoteRef:
        key: kakeibo-google-oauth-client-id
    - secretKey: GOOGLE_OAUTH_CLIENT_SECRET
      remoteRef:
        key: kakeibo-google-oauth-client-secret
    - secretKey: GMAIL_API_CLIENT_ID
      remoteRef:
        key: kakeibo-gmail-api-client-id
    - secretKey: GMAIL_API_CLIENT_SECRET
      remoteRef:
        key: kakeibo-gmail-api-client-secret
    - secretKey: GMAIL_API_REFRESH_TOKEN
      remoteRef:
        key: kakeibo-gmail-api-refresh-token
    - secretKey: NOTIFICATION_RECIPIENT_EMAIL
      remoteRef:
        key: kakeibo-notification-recipient-email
    - secretKey: MAIL_IMPORT_USER_EMAIL
      remoteRef:
        key: kakeibo-mail-import-user-email
```

- `secretStoreRef`: `infra-oci`側で構築済みの`ClusterSecretStore/oci-vault`（Instance Principal認証）を参照する
- `target.deletionPolicy: Retain`: ExternalSecretを削除しても、稼働中のPodが参照するSecretは削除しない
- `data[].remoteRef.key`: 3.3.2で登録したVaultのシークレット名

#### 3.3.4. ExternalSecretを適用して同期を確認する

`app-prod`ネームスペース（基盤側で作成済み）が存在することを確認したうえで、クラスタのノード上で適用する。

```bash
kubectl apply -f k8s/vault-sync.yaml
```

同期状態を確認する。

```bash
kubectl get externalsecret -n app-prod
```

- 1つ目のコマンド: ExternalSecretを作成する
- 2つ目のコマンド: `STATUS`が`SecretSynced`、`READY`が`True`であることを確認する

`kakeibo-secrets`のキーが3.3.2の11件であることを確認する。

```bash
kubectl get secret kakeibo-secrets -n app-prod -o jsonpath='{.data}' \
  | python3 -c 'import sys,json; print(sorted(json.load(sys.stdin).keys()))'
```

- Secretのキー名のみを一覧表示する（値は表示しない）

### 3.4. Web Deployment・Serviceを作成する

`k8s/web.yaml`を新規作成する。

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kakeibo-web
  namespace: app-prod
spec:
  replicas: 1
  selector:
    matchLabels:
      app: kakeibo-web
  template:
    metadata:
      labels:
        app: kakeibo-web
    spec:
      volumes:
        - name: mysqld-socket-dir
          hostPath:
            path: /var/run/mysqld
            type: Directory
      initContainers:
        - name: fix-mysqld-socket-permission
          image: busybox:1.36
          command:
            - sh
            - -c
            - |
              until [ -S /var/run/mysqld/mysqld.sock ]; do
                echo "waiting for mysqld.sock..."
                sleep 1
              done
              chmod 666 /var/run/mysqld/mysqld.sock
          securityContext:
            runAsUser: 0
          volumeMounts:
            - name: mysqld-socket-dir
              mountPath: /var/run/mysqld
      containers:
        - name: web
          image: kakeibo:latest # REPLACE_WITH_ACTUAL_IMAGE_TAG
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: kakeibo-config
            - secretRef:
                name: kakeibo-secrets
          volumeMounts:
            - name: mysqld-socket-dir
              mountPath: /var/run/mysqld
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
          readinessProbe:
            httpGet:
              path: /
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 30
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi
---
apiVersion: v1
kind: Service
metadata:
  name: kakeibo-web
  namespace: app-prod
spec:
  selector:
    app: kakeibo-web
  ports:
    - port: 80
      targetPort: 8000
```

- initContainerは基本設計書4.1.1節のとおり、ソケットファイル生成前のPod起動に備え
  ソケット出現を待ってから`chmod 666`でパーミッションを調整する
- `readinessProbe`・`livenessProbe`は未ログイン時のログイン画面へのリダイレクト
  （HTTPステータス302）を正常応答として扱う（`httpGet`は200〜399を成功とみなす）

### 3.5. メール取込CronJobを作成する

`k8s/cronjob-mail-import.yaml`を新規作成する。Web Deploymentと同じ
`mysqld-socket-dir`のhostPathマウント・initContainerを持つ構成とする。

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: kakeibo-mail-import
  namespace: app-prod
spec:
  schedule: "0 6 * * *"
  timeZone: "Asia/Tokyo"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 0
      template:
        spec:
          restartPolicy: Never
          volumes:
            - name: mysqld-socket-dir
              hostPath:
                path: /var/run/mysqld
                type: Directory
          initContainers:
            - name: fix-mysqld-socket-permission
              image: busybox:1.36
              command:
                - sh
                - -c
                - |
                  until [ -S /var/run/mysqld/mysqld.sock ]; do
                    echo "waiting for mysqld.sock..."
                    sleep 1
                  done
                  chmod 666 /var/run/mysqld/mysqld.sock
              securityContext:
                runAsUser: 0
              volumeMounts:
                - name: mysqld-socket-dir
                  mountPath: /var/run/mysqld
          containers:
            - name: mail-import
              image: kakeibo:latest # REPLACE_WITH_ACTUAL_IMAGE_TAG（web.yamlと同一イメージ）
              command: ["python", "manage.py", "import_transactions_from_mail"]
              envFrom:
                - configMapRef:
                    name: kakeibo-config
                - secretRef:
                    name: kakeibo-secrets
              volumeMounts:
                - name: mysqld-socket-dir
                  mountPath: /var/run/mysqld
              securityContext:
                runAsNonRoot: true
                runAsUser: 1000
              resources:
                requests:
                  cpu: 100m
                  memory: 128Mi
                limits:
                  cpu: 500m
                  memory: 256Mi
```

- 実行時刻（`schedule: "0 6 * * *"`）は決済通知メールが出揃う時間帯を想定した仮の値であり、
  運用開始後に実データを見て要調整

### 3.6. マニフェストの構文を確認する

```bash
python3 -c "
import yaml, glob
for f in sorted(glob.glob('k8s/*.yaml')):
    with open(f) as fh:
        list(yaml.safe_load_all(fh))
    print(f, 'OK')
"
```

- YAML構文の妥当性のみを確認する（実クラスタでの`kubectl apply --dry-run`による
  スキーマ検証は、クラスタへの接続経路が確立してから別途行う）

### 3.7. 共有Namespaceへ移行する

旧`kakeibo`ネームスペースで稼働していた環境を、共有の`app-prod`へ移行する。
旧Ingressが共有Ingressと同一ホスト・同一パスで重複するため、旧ネームスペースの削除が先である。
削除から共有Ingress作成までの間、`/kakeibo`は一時的に停止する。

クラスタのノード上で、旧ネームスペースを削除する。

```bash
kubectl delete namespace kakeibo
```

- 旧ネームスペース内のDeployment・Service・Ingress・CronJob・ExternalSecretをまとめて削除する

リポジトリのルートで、`app-prod`へデプロイする。

```bash
./deploy-oci.sh
```

- イメージのビルド・転送、マニフェスト適用、ロールアウト待機、マイグレーションを行う

`infra-oci`のリポジトリで、共有Ingressを作成する。

```bash
./scripts/run_ansible.sh --tags kubernetes
```

- 共有Ingressを作成し、`https://technohonesty.com/kakeibo/`を有効にする

動作を確認する。

```bash
kubectl get externalsecret,pods,ingress,certificate -n app-prod
```

- ExternalSecretが`SecretSynced`、Podが`Running`、共有Ingressと証明書が存在することを確認する
