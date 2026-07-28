// esbuild で src/entry.js を単一の dist/Code.gs にバンドルする。
// GASはESモジュールのimport/exportを実行時解釈できず、トリガー対象はトップレベルの
// グローバル関数である必要があるため、IIFE + footer でグローバル関数を露出させる。

import * as esbuild from 'esbuild';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';

await esbuild.build({
  entryPoints: ['src/entry.js'],
  bundle: true,
  format: 'iife',
  globalName: 'App',
  target: 'es2019',
  charset: 'utf8',
  outfile: 'dist/Code.gs',
  footer: {
    js: [
      'function main(){return App.main()}',
      'function cleanup(){return App.cleanup()}',
      'function setupTrigger(){return App.setupTrigger()}',
    ].join('\n'),
  },
});

mkdirSync('dist', { recursive: true });
// copyFileSyncはOSのネイティブcopyfile APIを使うため、ネットワーク越しの共有
// ファイルシステム(Mac<->この開発コンテナ間)でEPERMになることがある。
// read+writeなら単純なopen/writeで済むため、esbuildのoutfile書き込みと同様に安定する。
writeFileSync('dist/appsscript.json', readFileSync('appsscript.json'));
console.log('ビルド完了: dist/Code.gs, dist/appsscript.json');
