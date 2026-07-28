// ローカル(Node)アダプタ。ドライラン（push前の全工程ローカル実行）用。
// GASの UrlFetchApp は同期のため、こちらも同期I/O（curl の execSync）で揃える。
// 文字コードは Node標準の TextDecoder('shift_jis') で復号（full-ICU同梱のNodeが前提）。

import { execSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

function curlBytes(url) {
  return execSync(`curl -s --max-time 30 ${JSON.stringify(url)}`, { maxBuffer: 32 * 1024 * 1024 });
}

export function createNodeAdapter({ outDir }) {
  const dbPath = join(outDir, 'observations.csv');
  const imgDir = join(outDir, 'images');
  mkdirSync(imgDir, { recursive: true });

  return {
    fetchText(url) {
      return new TextDecoder('shift_jis').decode(curlBytes(url));
    },
    fetchBytes(url) {
      return curlBytes(url);
    },
    hasObservedAt(observedAt) {
      if (!existsSync(dbPath)) return false;
      return readFileSync(dbPath, 'utf-8')
        .split('\n')
        .some((line) => line.startsWith(`${observedAt},`));
    },
    saveImage(filename, bytes) {
      const p = join(imgDir, filename);
      writeFileSync(p, bytes);
      return p;
    },
    appendObservation(row) {
      const line = [
        row.observed_at, row.captured_at, row.cumulative_rainfall, row.temperature,
        row.wind_speed, row.road_temperature, row.road_condition ?? '',
        row.image_filename, row.image_ref, row.image_url, row.location_name,
        new Date().toISOString(),
      ].join(',');
      writeFileSync(dbPath, `${line}\n`, { flag: 'a' });
    },
    log(m) {
      console.log('[node]', m);
    },
  };
}
