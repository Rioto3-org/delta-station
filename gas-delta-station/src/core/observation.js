// 生データを検証済み観測データへ変換（Python: ObservationData の構築 + validator 相当）。
// 不正値は例外を投げる（Pydantic の ValidationError と同じ思想 = レコードごと弾く）。

import { normalizeNumeric, normalizeRoadCondition } from './normalize.js';
import { buildImageFilename } from './filename.js';

const DT_RE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;

function validateDatetime(s, label) {
  if (!DT_RE.test(s)) throw new Error(`${label}の形式が不正です: ${s}`);
  const [date, time] = s.split(' ');
  const [y, mo, d] = date.split('-').map(Number);
  const [h, mi] = time.split(':').map(Number);
  // Dateはオーバーフローを正規化する（例: 2月30日→3月2日）ため、往復比較で実在しない日付を弾く
  const dt = new Date(y, mo - 1, d, h, mi);
  const valid = dt.getFullYear() === y && dt.getMonth() === mo - 1 && dt.getDate() === d
    && dt.getHours() === h && dt.getMinutes() === mi;
  if (!valid) {
    throw new Error(`${label}の値が不正です: ${s}`);
  }
  return s;
}

function inRange(value, min, max, label) {
  if (value === null) return null;
  if (value < min || value > max) {
    throw new Error(`${label}が範囲外です: ${value} (許容 ${min}〜${max})`);
  }
  return value;
}

/**
 * 生データ + location_id -> 検証済み観測データ。
 * @param {object} raw parseHtml の戻り値
 * @param {number} locationId
 * @returns {object} DB/シートのカラムに対応した検証済みレコード
 * @throws {Error} 範囲外・形式不正の場合
 */
export function buildObservation(raw, locationId) {
  validateDatetime(raw.observed_at, '観測日時');
  validateDatetime(raw.captured_at, '撮影日時');

  const cumulative_rainfall = inRange(
    normalizeNumeric(raw.cumulative_rainfall, { allowNegative: false }), 0, 1000, '累加雨量');
  const temperature = inRange(
    normalizeNumeric(raw.temperature), -50, 50, '気温');
  const wind_speed = inRange(
    normalizeNumeric(raw.wind_speed, { allowNegative: false }), 0, 100, '風速');
  const road_temperature = inRange(
    normalizeNumeric(raw.road_temperature), -50, 80, '路面温度');
  const road_condition = normalizeRoadCondition(raw.road_condition);

  const image_filename = buildImageFilename(raw.observed_at, raw.image_url);

  return {
    location_id: locationId,
    observed_at: raw.observed_at,
    captured_at: raw.captured_at,
    cumulative_rainfall,
    temperature,
    wind_speed,
    road_temperature,
    road_condition,
    image_filename,
    image_url: raw.image_url,
  };
}
