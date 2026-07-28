// HTML から生データを抽出（Python: ScrapedRawData.from_html 相当）。
// GASにはBeautifulSoupが無いため正規表現ベース。GAS非依存の純粋関数。
// 入力の html は「デコード済み文字列」（Shift_JISの復号はアダプタ層の責務）。

function decodeEntities(s) {
  return s
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"');
}

function stripTags(s) {
  return decodeEntities(s.replace(/<[^>]+>/g, '')).trim();
}

/**
 * 相対URLを絶対URLへ解決（Python: urljoin 相当。今回の入力パターンに必要な範囲）。
 * GASのV8には URL クラスが無いため手書き。
 */
export function resolveUrl(base, src) {
  if (/^https?:\/\//i.test(src)) return src;
  const m = /^(https?:\/\/[^/]+)(\/[^?#]*)?/i.exec(base);
  if (!m) return src;
  const origin = m[1];
  let path = m[2] || '/';
  if (src.startsWith('/')) return origin + src;
  path = path.replace(/[^/]*$/, ''); // 末尾セグメント（ファイル名）を除去
  return origin + path + src;
}

const LABEL_MAP = {
  観測地点: 'location_name',
  累加雨量: 'cumulative_rainfall',
  気温: 'temperature',
  風速: 'wind_speed',
  路面温度: 'road_temperature',
  路面状況: 'road_condition',
};

/**
 * HTMLから観測生データを抽出する。
 * @param {string} html デコード済みHTML文字列
 * @param {string} sourceUrl 取得元URL（画像URLの絶対化に使用）
 * @returns {object} 生データ（数値は "5.0℃" などの文字列のまま）
 * @throws {Error} 必須項目が抽出できない場合
 */
export function parseHtml(html, sourceUrl) {
  // 観測日時: "観測日時：2026-07-27 21:50"
  let m = /観測日時[：:]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})/.exec(html);
  if (!m) throw new Error('観測日時が見つかりません');
  const observed_at = m[1].trim();

  // 撮影日時: "撮影日時：07/27 21:52" → 年は観測日時から借用して "YYYY-MM-DD HH:MM"
  m = /撮影日時[：:]\s*(\d{2}\/\d{2})\s+(\d{2}:\d{2})/.exec(html);
  if (!m) throw new Error('撮影日時が見つかりません');
  const year = observed_at.slice(0, 4);
  const captured_at = `${year}-${m[1].replace('/', '-')} ${m[2]}`;

  // 住所: 最初の class に style3 を含む div
  let location_address = '不明';
  const dm = /<div[^>]*class="[^"]*\bstyle3\b[^"]*"[^>]*>([\s\S]*?)<\/div>/i.exec(html);
  if (dm) location_address = stripTags(dm[1]);

  // テーブル各行の <td>ラベル</td><td>値</td> をラベル完全一致で抽出
  // （"※ 累加雨量説明" 等も2-td構造だが、完全一致なので誤爆しない）
  const fields = {
    location_name: null,
    cumulative_rainfall: null,
    temperature: null,
    wind_speed: null,
    road_temperature: null,
    road_condition: null,
  };
  const trRe = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
  let tr;
  while ((tr = trRe.exec(html)) !== null) {
    const tds = [...tr[1].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gi)].map((x) => stripTags(x[1]));
    if (tds.length === 2) {
      const key = LABEL_MAP[tds[0]];
      if (key) fields[key] = tds[1];
    }
  }
  if (!fields.location_name) throw new Error('観測地点名が見つかりません');

  // 画像URL: <img src="image/DR-74125-l.jpg" ...>
  const im = /<img[^>]*src="([^"]*DR-\d+-l\.jpg)"[^>]*>/i.exec(html);
  if (!im) throw new Error('画像URLが見つかりません');
  const image_url = resolveUrl(sourceUrl, im[1]);

  return {
    location_name: fields.location_name,
    location_address,
    observed_at,
    captured_at,
    cumulative_rainfall: fields.cumulative_rainfall,
    temperature: fields.temperature,
    wind_speed: fields.wind_speed,
    road_temperature: fields.road_temperature,
    road_condition: fields.road_condition,
    image_url,
  };
}
