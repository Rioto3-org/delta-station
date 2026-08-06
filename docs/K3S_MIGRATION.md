# k3s移行記録（履歴）

この文書は、docker-composeからk3sへ移行した時点の計画・判断を残す履歴文書である。現行の運用手順は[OPERATIONS.md](OPERATIONS.md)と[DEPLOYMENT.md](DEPLOYMENT.md)を参照する。

現在の重要な変更点は以下の通り。

- 取得処理は旧PythonスクレイパーではなくGASが担当する。
- k3sのImporter CronJobはGASバッファからPostgreSQLへ取り込む。
- 旧SQLiteはPVC上に残るが、通常運用の書き込み先ではない。
