# 旧設計書

この文書は、SQLiteと旧Pythonスクレイパーを前提にした初期設計の履歴である。現行仕様ではない。

現行の正本は以下を参照する。

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [DATA_MODEL.md](DATA_MODEL.md)
- [OPERATIONS.md](OPERATIONS.md)
- [MIGRATION.md](MIGRATION.md)

旧設計からの主な変更点は、スクレイピングをGASへ移し、DBをPostgreSQLへ移行し、画像を`observations.image_data`へ保存したことである。
