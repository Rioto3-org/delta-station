// スクレイピングの全体フロー（Python: scraper.py の main() 相当）。
// I/O は adapter 経由に抽象化しているため、GAS でもローカル(Node)でも同一コードが動く。
// 注意: GAS の UrlFetchApp 等は同期APIのため、この関数は同期で書く（adapterも同期実装）。

import { parseHtml } from './core/parse.js';
import { buildObservation } from './core/observation.js';

/**
 * @param {object} adapter fetchText, fetchBytes, hasObservedAt, saveImage, appendObservation, log を実装
 * @param {object} config CONFIG（sourceUrl, locationId, locationName, sheetName）
 * @returns {{status: 'inserted'|'skip', observation: object, imageRef?: any}}
 */
export function runScrape(adapter, config) {
  const html = adapter.fetchText(config.sourceUrl);
  const raw = parseHtml(html, config.sourceUrl);
  const obs = buildObservation(raw, config.locationId);

  // 冪等性: observed_at が既存ならスキップ（DBの UNIQUE 制約に相当）
  if (adapter.hasObservedAt(obs.observed_at)) {
    adapter.log(`データ未更新（既存）: ${obs.observed_at}`);
    return { status: 'skip', observation: obs };
  }

  // 画像は「取得時点」に必ず保存する（元画像は固定パスで上書きされ後から取得不可のため）
  const bytes = adapter.fetchBytes(obs.image_url);
  const imageRef = adapter.saveImage(obs.image_filename, bytes);

  adapter.appendObservation({
    ...obs,
    location_name: config.locationName,
    image_ref: imageRef,
  });
  adapter.log(`新規データ挿入: ${obs.observed_at}`);
  return { status: 'inserted', observation: obs, imageRef };
}
