.PHONY: run install-cron uninstall-cron status test test-db clean help

.DEFAULT_GOAL := help

help: ## このヘルプメッセージを表示
	@echo "Delta地点 観測データベースシステム"
	@echo ""
	@echo "利用可能なコマンド:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36mmake %-15s\033[0m %s\n", $$1, $$2}'

run: ## 本番スクリプトを実行（cronから呼ばれる）
	@python3 src/scraper.py

test: ## スクレイピングテストを実行
	@python3 tests/test_scraper.py

test-db: ## データベース挿入テストを実行
	@python3 tests/test_db_insert.py

install-cron: ## cronジョブをインストール（15分間隔）
	@echo "cronジョブを設定します..."
	@(crontab -l 2>/dev/null | grep -v "delta-station"; \
	  echo "*/15 * * * * cd $(shell pwd) && make run >> $(shell pwd)/outputs/scraper.log 2>&1") | crontab -
	@echo "✓ cronジョブを設定しました（15分間隔）"
	@echo ""
	@echo "設定内容:"
	@crontab -l | grep delta-station

uninstall-cron: ## cronジョブを削除
	@echo "cronジョブを削除します..."
	@crontab -l 2>/dev/null | grep -v "delta-station" | crontab -
	@echo "✓ cronジョブを削除しました"

status: ## cronジョブの状態を確認
	@echo "現在のcronジョブ:"
	@crontab -l 2>/dev/null | grep delta-station || echo "  未設定"
	@echo ""
	@echo "最新のログ（最後の10行）:"
	@tail -n 10 outputs/scraper.log 2>/dev/null || echo "  ログファイルなし"

clean: ## 生成ファイルを削除
	@echo "クリーンアップ中..."
	@rm -rf __pycache__
	@rm -rf src/__pycache__
	@rm -rf tests/__pycache__
	@find . -type f -name "*.pyc" -delete
	@echo "✓ クリーンアップ完了"
