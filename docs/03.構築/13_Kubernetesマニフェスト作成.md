# 13 構築手順書 - Kubernetesマニフェスト作成

## 目次

- [1. 概要](#1-概要)
- [2. 前提条件](#2-前提条件)
- [3. 手順](#3-手順)
  - [3.1. FORCE_SCRIPT_NAMEを設定する](#31-force_script_nameを設定する)
  - [3.2. Namespaceを作成する](#32-namespaceを作成する)
  - [3.3. ConfigMapを作成する](#33-configmapを作成する)
  - [3.4. SecretStore・ExternalSecretを作成する](#34-secretstoreexternalsecretを作成する)
  - [3.5. Web Deployment・Serviceを作成する](#35-web-deploymentserviceを作成する)
  - [3.6. Ingressを作成する](#36-ingressを作成する)
  - [3.7. メール取込CronJobを作成する](#37-メール取込cronjobを作成する)
  - [3.8. バックアップCronJobを作成する](#38-バックアップcronjobを作成する)
  - [3.9. マニフェストの構文を確認する](#39-マニフェストの構文を確認する)

## 1. 概要

対応Issue: [#29](https://github.com/Seiya-Nakagawa/kakeibo/issues/29)

Web Pod・CronJob（メール取込、バックアップ）のKubernetesマニフェストを作成する。
対応する設計書: [基本設計書4.1.1節](../02.設計/基本設計書.md#411-pod-から-mysql-への接続方式)、
[1.1.1節](../02.設計/基本設計書.md#111-ドメインパス割り当て方針)、
[7.3節](../02.設計/基本設計書.md#73-セキュリティ要件-63)

**注意**: 以下は実クラスタでの検証（`kubectl apply`）ができていない。特に次の3点は
実際のクラスタ構成（`infra-oci-terraform`・`infra-oci-ansible`側の設定）に合わせて
要確認・要調整である。

- `k8s/web.yaml`・`k8s/cronjob-*.yaml`の`image`（コンテナイメージのレジストリ・タグ）
- `k8s/external-secret.yaml`のExternal Secrets Operator認証方式
  （導入済みバージョンのスキーマに依存する）
- `k8s/ingress.yaml`の証明書Secret名（他アプリと共有するドメインのため、
  既存のCertificateリソースを参照する可能性がある）

## 2. 前提条件

- [12_バックアップ用CronJob実装.md](12_バックアップ用CronJob実装.md) の完了
- `infra-oci-terraform`・`infra-oci-ansible`によりKubernetesクラスタ・
  ingress-nginx・cert-manager・External Secrets Operatorが構築済みであること

## 3. 手順

### 3.1. FORCE_SCRIPT_NAMEを設定する

`webapp/config/settings/production.py`に以下を追加する。

```python
# 基本設計書1.1.1節: /kakeibo配下で動作させるため、URL逆引き・リダイレクト先に
# プレフィックスを付与する。Ingress側は/kakeiboを除去してバックエンドへ転送する
# （k8s/ingress.yamlのrewrite-target）ため、Django側は付与のみを担う。
FORCE_SCRIPT_NAME = env("FORCE_SCRIPT_NAME", default="/kakeibo")
```

`webapp/.env.example`のコメントアウト済み本番専用設定に以下を追記する。

```dotenv
# FORCE_SCRIPT_NAME=/kakeibo
```

### 3.2. Namespaceを作成する

`k8s/namespace.yaml`を新規作成する。

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: kakeibo
```

### 3.3. ConfigMapを作成する

`k8s/configmap.yaml`を新規作成する。機密情報を含まない設定値のみを保持する。

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kakeibo-config
  namespace: kakeibo
data:
  ALLOWED_HOSTS: "technohonesty.com"
  FORCE_SCRIPT_NAME: "/kakeibo"
  DB_SOCKET_PATH: "/var/run/mysqld/mysqld.sock"
  SESSION_TIMEOUT_SECONDS: "1800"
```

### 3.4. SecretStore・ExternalSecretを作成する

`k8s/external-secret.yaml`を新規作成する。OCI Vaultの各シークレットを
`kakeibo-secrets`という1つのKubernetes Secretへ同期する。

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: oci-vault
  namespace: kakeibo
spec:
  provider:
    oracle:
      vault: "ocid1.vault.oc1..REPLACE_WITH_ACTUAL_VAULT_OCID"
      region: "ap-tokyo-1"
      auth:
        instancePrincipal: {}
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: kakeibo-secrets
  namespace: kakeibo
spec:
  secretStoreRef:
    name: oci-vault
    kind: SecretStore
  target:
    name: kakeibo-secrets
    creationPolicy: Owner
  refreshInterval: 1h
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
    - secretKey: BACKUP_S3_ENDPOINT_URL
      remoteRef:
        key: kakeibo-backup-s3-endpoint-url
    - secretKey: BACKUP_S3_ACCESS_KEY
      remoteRef:
        key: kakeibo-backup-s3-access-key
    - secretKey: BACKUP_S3_SECRET_KEY
      remoteRef:
        key: kakeibo-backup-s3-secret-key
    - secretKey: BACKUP_S3_REGION
      remoteRef:
        key: kakeibo-backup-s3-region
    - secretKey: BACKUP_BUCKET_NAME
      remoteRef:
        key: kakeibo-backup-bucket-name
```

- `data[].remoteRef.key`は、OCI Vault側に同名のシークレットを事前登録しておく前提の値である

### 3.5. Web Deployment・Serviceを作成する

`k8s/web.yaml`を新規作成する。

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kakeibo-web
  namespace: kakeibo
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
  namespace: kakeibo
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

### 3.6. Ingressを作成する

`k8s/ingress.yaml`を新規作成する。

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: kakeibo-web
  namespace: kakeibo
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /$2
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - technohonesty.com
      secretName: technohonesty-com-tls
  rules:
    - host: technohonesty.com
      http:
        paths:
          - path: /kakeibo(/|$)(.*)
            pathType: ImplementationSpecific
            backend:
              service:
                name: kakeibo-web
                port:
                  number: 80
```

- `/kakeibo(/|$)(.*)`と`rewrite-target: /$2`の組み合わせで、`/kakeibo`プレフィックスを
  除去してバックエンド（Django、`FORCE_SCRIPT_NAME`側で`/kakeibo`を再付与）へ転送する
  （基本設計書1.1.1節）

### 3.7. メール取込CronJobを作成する

`k8s/cronjob-mail-import.yaml`を新規作成する。Web Deploymentと同じ
`mysqld-socket-dir`のhostPathマウント・initContainerを持つ構成とする。

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: kakeibo-mail-import
  namespace: kakeibo
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

### 3.8. バックアップCronJobを作成する

`k8s/cronjob-backup.yaml`を新規作成する。構成は3.7と同様で、`command`のみ
`["python", "manage.py", "backup_database"]`に、`schedule`を`"0 3 * * *"`
（メール取込より後、DBへの日中の書き込みが少ない時間帯を想定した仮の値）に変更する。

### 3.9. マニフェストの構文を確認する

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
