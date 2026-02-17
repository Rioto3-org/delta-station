.PHONY: help start run stop status docker-build docker-start docker-stop docker-restart docker-logs docker-status docker-clean docker-dashboard docker-dashboard-logs

.DEFAULT_GOAL := help

help: ## このヘルプメッセージを表示
	@echo "Delta地点 観測データベースシステム"
	@echo ""
	@echo "=== ローカル実行（開発用） ==="
	@grep -E '^(start|run|stop|status):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36mmake %-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "=== Docker実行（本番用） ==="
	@grep -E '^docker-.*:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36mmake %-20s\033[0m %s\n", $$1, $$2}'

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

# ========================================
# Docker実行（本番用）
# ========================================

docker-build: ## [Docker] イメージをビルド
	@echo "Dockerイメージをビルドします..."
	docker compose build

docker-start: ## [Docker] コンテナを起動（15分間隔で自動実行）
	@echo "Delta地点観測コンテナを起動します..."
	docker compose up -d
	@echo "✓ コンテナを起動しました"
	@echo ""
	@echo "ログを確認: make docker-logs"
	@echo "状態を確認: make docker-status"

docker-stop: ## [Docker] コンテナを停止
	@echo "Delta地点観測コンテナを停止します..."
	docker compose down
	@echo "✓ コンテナを停止しました"

docker-restart: docker-stop docker-start ## [Docker] コンテナを再起動

docker-logs: ## [Docker] コンテナのログをリアルタイム表示
	docker compose logs -f scraper

docker-status: ## [Docker] コンテナの状態を確認
	@echo "=== コンテナ状態 ==="
	@docker compose ps
	@echo ""
	@echo "=== 最新ログ（最後の20行） ==="
	@docker compose logs --tail=20 scraper

docker-clean: docker-stop ## [Docker] コンテナ・イメージ・ボリュームを完全削除
	@echo "Docker環境をクリーンアップします..."
	docker compose down -v
	docker rmi delta-station-scraper 2>/dev/null || true
	@echo "✓ クリーンアップ完了"

docker-dashboard: ## [Docker] ダッシュボードのみ起動 (http://localhost:8350)
	@echo "Delta地点ダッシュボードを起動します..."
	docker compose up -d dashboard
	@echo "✓ ダッシュボードを起動しました"
	@echo ""
	@echo "🌡️  アクセス: http://localhost:8350"
	@echo ""
	@echo "ログを確認: make docker-dashboard-logs"

docker-dashboard-logs: ## [Docker] ダッシュボードのログをリアルタイム表示
	docker compose logs -f dashboard
