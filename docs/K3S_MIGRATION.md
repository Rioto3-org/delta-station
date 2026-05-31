# k3s 移行計画

docker-compose 構成から k3s への移行計画。

## 移行の背景と方針

### 現状（docker-compose）

| コンポーネント | 現状 | 課題 |
|---|---|---|
| スクレイパー | `while true; sleep 900` のループ | 実行履歴なし、ログ管理が雑 |
| ダッシュボード | コンテナ常駐 | 特になし |
| データ永続化 | `./outputs` ボリュームマウント | 特になし |

### 移行後（k3s）

| コンポーネント | 移行後 |
|---|---|
| スクレイパー | **CronJob**（15分ごとにPod起動→実行→終了） |
| ダッシュボード | **Deployment + Service**（NodePortで8350公開） |
| データ永続化 | **PersistentVolumeClaim**（local-path、既存outputsディレクトリ） |

### SQLiteについて

移行しない。理由：
- シングルライター（スクレイパーは同時実行しない）
- 15分間隔の低頻度書き込み
- ファイルベースなのでPVCにそのまま乗る
- `observed_at` のUNIQUE制約で重複は完全防止済み

---

## 変更が必要なファイル

### 1. `Dockerfile.scraper` のCMD変更

CronJobはコンテナが1回実行して終了することを前提とする。sleepループを除去。

**Before:**
```dockerfile
CMD ["/bin/sh", "-c", "while true; do ... sleep 900; done"]
```

**After:**
```dockerfile
CMD ["uv", "run", "python", "-m", "src.collector.scraper"]
```

`main()` は既に `return 0/1` で終わる設計なので、コード変更は不要。

### 2. k8s マニフェスト新規作成（`k8s/` ディレクトリ）

---

## マニフェスト設計

### PersistentVolumeClaim

```yaml
# k8s/pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: delta-station-outputs
  namespace: delta-station
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path   # k3sデフォルト
  resources:
    requests:
      storage: 20Gi
```

### スクレイパー（CronJob）

```yaml
# k8s/scraper-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: delta-station-scraper
  namespace: delta-station
spec:
  schedule: "*/15 * * * *"
  concurrencyPolicy: Forbid       # 前の実行が終わってなければスキップ
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: scraper
              image: delta-station-scraper:latest
              imagePullPolicy: Never   # ローカルイメージ
              env:
                - name: TZ
                  value: Asia/Tokyo
                - name: PYTHONUNBUFFERED
                  value: "1"
              volumeMounts:
                - name: outputs
                  mountPath: /app/outputs
          volumes:
            - name: outputs
              persistentVolumeClaim:
                claimName: delta-station-outputs
```

**ポイント:**
- `concurrencyPolicy: Forbid` → 前回実行が詰まっても次が被らない
- `restartPolicy: OnFailure` → 失敗時はPodを再起動（ただしscraperは失敗してもほぼない）
- `imagePullPolicy: Never` → 自宅サーバなのでローカルビルドイメージを使う

### ダッシュボード（Deployment + Service）

```yaml
# k8s/dashboard-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: delta-station-dashboard
  namespace: delta-station
spec:
  replicas: 1
  selector:
    matchLabels:
      app: delta-station-dashboard
  template:
    metadata:
      labels:
        app: delta-station-dashboard
    spec:
      containers:
        - name: dashboard
          image: delta-station-dashboard:latest
          imagePullPolicy: Never
          ports:
            - containerPort: 8501
          env:
            - name: TZ
              value: Asia/Tokyo
            - name: PYTHONUNBUFFERED
              value: "1"
          volumeMounts:
            - name: outputs
              mountPath: /app/outputs
      volumes:
        - name: outputs
          persistentVolumeClaim:
            claimName: delta-station-outputs
---
apiVersion: v1
kind: Service
metadata:
  name: delta-station-dashboard
  namespace: delta-station
spec:
  type: NodePort
  selector:
    app: delta-station-dashboard
  ports:
    - port: 8501
      targetPort: 8501
      nodePort: 30350   # 既存の8350と対応させる
```

### Namespace

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: delta-station
```

---

## 移行手順

### Phase 1: 準備（docker-compose停止前）

- [ ] k3sインストール済みであること確認
- [ ] 既存データのバックアップ
  ```bash
  tar -czf delta-station-backup-$(date +%Y%m%d).tar.gz outputs/
  ```
- [ ] ローカルイメージのビルド
  ```bash
  docker build -f Dockerfile.scraper -t delta-station-scraper:latest .
  docker build -f Dockerfile.dashboard -t delta-station-dashboard:latest .
  ```
- [ ] k3sへのイメージインポート
  ```bash
  docker save delta-station-scraper:latest | sudo k3s ctr images import -
  docker save delta-station-dashboard:latest | sudo k3s ctr images import -
  ```

### Phase 2: データ移行

既存の `./outputs/` ディレクトリをPVCのパスに配置する。

k3sのlocal-pathのデフォルト保存先: `/var/lib/rancher/k3s/storage/`

```bash
# namespaceとPVC作成
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/pvc.yaml

# PVCがバインドされたらパスを確認
kubectl get pv -n delta-station
# → /var/lib/rancher/k3s/storage/<pvc-name>/ が確認できる

# 既存データをコピー
sudo cp -r outputs/* /var/lib/rancher/k3s/storage/<pvc-name>/
```

### Phase 3: docker-compose停止 → k3s起動

```bash
# docker-compose停止
docker compose -f docker-compose.yml down
docker compose -f docker-compose.a.yml down

# k8sリソース適用
kubectl apply -f k8s/dashboard-deployment.yaml
kubectl apply -f k8s/scraper-cronjob.yaml

# 動作確認
kubectl get pods -n delta-station
kubectl logs -n delta-station deployment/delta-station-dashboard
```

### Phase 4: 動作確認

- [ ] ダッシュボードに `http://localhost:30350` でアクセスできる
- [ ] CronJobが15分後に自動実行されるか確認
  ```bash
  kubectl get cronjob -n delta-station
  kubectl get jobs -n delta-station --watch
  ```
- [ ] データが挿入されているか確認（ログで `新規データ挿入成功` が出ること）
- [ ] 重複チェック（同じ `observed_at` で2回実行してもエラーにならないこと）

---

## リスクと対策

| リスク | 対策 |
|---|---|
| PVCへのデータコピー失敗 | バックアップから復元（Phase 1で取得済み） |
| イメージのインポート失敗 | `k3s ctr images list` で確認、再インポート |
| NodePortが既存の8350と競合 | 30350を使用（NodePortは30000-32767の範囲） |
| CronJobのタイミングがずれる | `*/15` は毎時0,15,30,45分起動。許容範囲 |

---

## 今後の検討事項

- **Ingress化**: NodePortからIngressへの移行（ドメイン名でアクセスしたい場合）
- **イメージレジストリ**: ローカルレジストリ（`registry:2`）の導入でイメージ管理を楽に
- **Helmチャート化**: マニフェストが増えてきたら検討
