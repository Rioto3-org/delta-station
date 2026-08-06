// ローカルで全工程を実行する（clasp push 不要）。
// 実サイトを取得 → パース → 正規化 → .dry-run-out/ にCSVと画像を保存。
// 使い方: npm run dry-run

import { fileURLToPath } from 'node:url';
import { runScrape } from '../src/pipeline.js';
import { createNodeAdapter } from '../src/adapters/node.js';
import { CONFIG } from '../src/core/config.js';

const outDir = fileURLToPath(new URL('../.dry-run-out/', import.meta.url));
const adapter = createNodeAdapter({ outDir });

const result = runScrape(adapter, CONFIG);
console.log('--- ドライラン結果 ---');
console.log(JSON.stringify(result, null, 2));
console.log(`出力先: ${outDir}`);
