.PHONY: help start run stop status docker-build docker-start docker-stop docker-restart docker-logs docker-status docker-clean docker-dashboard docker-dashboard-logs docker-scraper-a docker-scraper-a-stop docker-scraper-a-logs docker-scraper-b docker-scraper-b-stop docker-scraper-b-logs docker-switch-a-to-b docker-switch-b-to-a docker-status-all

.DEFAULT_GOAL := help

help: ## このヘルプメッセージを表示
	@echo "Delta地点 観測データベースシステム"
	@echo ""
	@echo "=== ローカル実行（開発用） ==="
	@grep -E '^(start|run|stop|status):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36mmake %-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "=== Docker実行（本番用） ==="
	@grep -E '^docker-.*:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36mmake %-30s\033[0m %s\n", $$1, $$2}'

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

docker-start: docker-scraper-a docker-dashboard ## [Docker] 全コンテナ起動（スクレイパーA + ダッシュボード）
	@echo "✓ 全コンテナを起動しました"

docker-stop: ## [Docker] 全コンテナ停止
	@echo "Delta地点観測コンテナを停止します..."
	docker compose down
	docker compose -f docker-compose.a.yml down
	docker compose -f docker-compose.b.yml down
	@echo "✓ コンテナを停止しました"

docker-restart: docker-stop docker-start ## [Docker] 全コンテナ再起動

docker-logs: docker-scraper-a-logs ## [Docker] スクレイパーAのログをリアルタイム表示

docker-status: docker-status-all ## [Docker] 全コンテナの状態を確認

docker-clean: docker-stop ## [Docker] コンテナ・イメージ・ボリュームを完全削除
	@echo "Docker環境をクリーンアップします..."
	docker compose down -v
	docker compose -f docker-compose.a.yml down -v
	docker compose -f docker-compose.b.yml down -v
	docker rmi delta-station-dashboard delta-station-scraper-a delta-station-scraper-b 2>/dev/null || true
	@echo "✓ クリーンアップ完了"

# ========================================
# ダッシュボード（共通）
# ========================================

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

# ========================================
# スクレイパーA（運用）
# ========================================

docker-scraper-a: ## [Docker] スクレイパーA起動（運用）
	@echo "スクレイパーA（運用中）を起動します..."
	docker compose -f docker-compose.a.yml up -d
	@echo "✓ スクレイパーAを起動しました"

docker-scraper-a-stop: ## [Docker] スクレイパーA停止
	@echo "スクレイパーAを停止します..."
	docker compose -f docker-compose.a.yml down
	@echo "✓ スクレイパーAを停止しました"

docker-scraper-a-logs: ## [Docker] スクレイパーAのログをリアルタイム表示
	docker compose -f docker-compose.a.yml logs -f

# ========================================
# スクレイパーB（開発・次期運用）
# ========================================

docker-scraper-b: ## [Docker] スクレイパーB起動（開発）
	@echo "スクレイパーB（開発中）を起動します..."
	docker compose -f docker-compose.b.yml up -d
	@echo "✓ スクレイパーBを起動しました"

docker-scraper-b-stop: ## [Docker] スクレイパーB停止
	@echo "スクレイパーBを停止します..."
	docker compose -f docker-compose.b.yml down
	@echo "✓ スクレイパーBを停止しました"

docker-scraper-b-logs: ## [Docker] スクレイパーBのログをリアルタイム表示
	docker compose -f docker-compose.b.yml logs -f

# ========================================
# スクレイパー切り替え
# ========================================

docker-switch-a-to-b: ## [Docker] A→B切り替え（B起動 → A停止）
	@echo "==================================================="
	@echo "運用をAからBに切り替えます..."
	@echo "==================================================="
	@echo ""
	@echo "[1/2] スクレイパーBを起動中..."
	@$(MAKE) -s docker-scraper-b
	@echo ""
	@sleep 3
	@echo "[2/2] スクレイパーAを停止中..."
	@$(MAKE) -s docker-scraper-a-stop
	@echo ""
	@echo "==================================================="
	@echo "✓ 切り替え完了: スクレイパーBが運用中です"
	@echo "==================================================="

docker-switch-b-to-a: ## [Docker] B→A切り替え（ロールバック）
	@echo "==================================================="
	@echo "運用をBからAに切り替えます（ロールバック）..."
	@echo "==================================================="
	@echo ""
	@echo "[1/2] スクレイパーAを起動中..."
	@$(MAKE) -s docker-scraper-a
	@echo ""
	@sleep 3
	@echo "[2/2] スクレイパーBを停止中..."
	@$(MAKE) -s docker-scraper-b-stop
	@echo ""
	@echo "==================================================="
	@echo "✓ ロールバック完了: スクレイパーAが運用中です"
	@echo "==================================================="

# ========================================
# 状態確認
# ========================================

docker-status-all: ## [Docker] 全コンテナの状態を確認
	@echo "==================================================="
	@echo "Delta地点 全コンテナ状態"
	@echo "==================================================="
	@echo ""
	@echo "[ダッシュボード]"
	@docker compose ps 2>/dev/null || echo "  停止中"
	@echo ""
	@echo "[スクレイパーA - 運用]"
	@docker compose -f docker-compose.a.yml ps 2>/dev/null || echo "  停止中"
	@echo ""
	@echo "[スクレイパーB - 開発]"
	@docker compose -f docker-compose.b.yml ps 2>/dev/null || echo "  停止中"
	@echo ""
	@echo "==================================================="
