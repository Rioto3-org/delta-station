.PHONY: start run stop status help

.DEFAULT_GOAL := help

help: ## このヘルプメッセージを表示
	@echo "Delta地点 観測データベースシステム"
	@echo ""
	@echo "利用可能なコマンド:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36mmake %-15s\033[0m %s\n", $$1, $$2}'

start: stop run ## 再起動（停止してから開始）

run: ## 15分間隔でバックグラウンド実行を開始（即座に1回実行 + cron設定）
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

stop: ## バックグラウンド実行を停止
	@echo "Delta地点観測データ収集を停止します..."
	@crontab -l 2>/dev/null | grep -v "delta-station" | crontab -
	@echo "✓ cronジョブを削除しました"

status: ## 実行状態とログを確認
	@echo "現在のcronジョブ:"
	@crontab -l 2>/dev/null | grep delta-station || echo "  未設定"
	@echo ""
	@echo "最新のログ（最後の20行）:"
	@tail -n 20 outputs/scraper.log 2>/dev/null || echo "  ログファイルなし"
