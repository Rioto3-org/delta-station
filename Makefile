.PHONY: help start run stop status import test-import deploy-dashboard deploy-importer run-importer k3s-status dashboard-logs

.DEFAULT_GOAL := help

help: ## このヘルプメッセージを表示
	@echo "Delta地点 観測データベースシステム"
	@echo ""
	@echo "=== ローカル実行（開発用） ==="
	@grep -E '^(start|run|stop|status|import|test-import|deploy-dashboard|deploy-importer|run-importer|k3s-status|dashboard-logs):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36mmake %-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "本番運用（k3s CronJob）は k3s-manifests/ を参照。"

# ========================================
# ローカル実行（開発用）
# ========================================

start: stop run ## [ローカル] 再起動（停止してから開始）

run: ## [ローカル] 15分間隔でバックグラウンド実行を開始
	@echo "Delta地点観測データ収集を開始します..."
	@echo ""
	@echo "1. 初回実行を開始..."
	@uv run python src/scraper.py
	@echo ""
	@echo "2. cronジョブを設定（15分間隔）..."
	@UV_PATH=$$(which uv); \
	 if [ -z "$$UV_PATH" ]; then \
	   echo "エラー: uvコマンドが見つかりません"; \
	   exit 1; \
	 fi; \
	 (crontab -l 2>/dev/null | grep -v "delta-station"; \
	  echo "*/15 * * * * cd $(shell pwd) && $$UV_PATH run python src/scraper.py >> $(shell pwd)/outputs/scraper.log 2>&1") | crontab -
	@echo "✓ cronジョブを設定しました"
	@echo ""
	@crontab -l | grep delta-station

stop: ## [ローカル] バックグラウンド実行を停止
	@echo "Delta地点観測データ収集を停止します..."
	@crontab -l 2>/dev/null | grep -v "delta-station" | crontab -
	@echo "✓ cronジョブを削除しました"

status: ## [ローカル] 実行状態とログを確認
	@echo "現在のcronジョブ:"
	@crontab -l 2>/dev/null | grep delta-station || echo "  未設定"
	@echo ""
	@echo "最新のログ（最後の20行）:"
	@tail -n 20 outputs/scraper.log 2>/dev/null || echo "  ログファイルなし"

import: ## [ローカル] GASバッファ(シート+Drive)からDBへ手動取り込み
	@uv run python -m src.collector.importer

test-import: ## [ローカル] importerの単体テスト（Google認証・ネットワーク不要）
	@uv run pytest tests/test_importer.py -v

# ========================================
# リモートK3s運用（クライアントからSSHで実行）
# ========================================

deploy-dashboard: ## [リモート] ローカルのdashboardをSSH経由でビルド・公開
	@DELTA_REMOTE="$(DELTA_REMOTE)" scripts/remote_k3s.sh deploy-dashboard

deploy-importer: ## [リモート] ローカルのImporterをSSH経由でビルド・適用
	@DELTA_REMOTE="$(DELTA_REMOTE)" scripts/remote_k3s.sh deploy-importer

run-importer: ## [リモート] Importerを一度だけ実行しログを表示
	@DELTA_REMOTE="$(DELTA_REMOTE)" scripts/remote_k3s.sh run-importer

k3s-status: ## [リモート] Pod・CronJob・Jobの状態を表示
	@DELTA_REMOTE="$(DELTA_REMOTE)" scripts/remote_k3s.sh status

dashboard-logs: ## [リモート] 起動中Dashboardのログを追跡
	@DELTA_REMOTE="$(DELTA_REMOTE)" scripts/remote_k3s.sh logs-dashboard
