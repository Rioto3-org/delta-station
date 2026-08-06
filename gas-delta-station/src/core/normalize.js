// 値の正規化（Python: ObservationData の各 field_validator 相当）
// GAS非依存の純粋関数。ローカルで単体テストする。

/**
 * 文字列から数値を抽出して返す（例: "5.0℃" -> 5.0, "1.8m/s" -> 1.8）。
 * 数値が無い / 空 / null の場合は null。
 * @param {string|number|null|undefined} value
 * @param {{allowNegative?: boolean}} [opts] 負値を許容するか（累加雨量・風速は false）
 * @returns {number|null}
 */
export function normalizeNumeric(value, { allowNegative = true } = {}) {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number') return value;
  const re = allowNegative ? /-?[\d.]+/ : /[\d.]+/;
  const m = re.exec(String(value));
  return m ? parseFloat(m[0]) : null;
}

/**
 * 路面状況の正規化。'----' と空は「データなし」= null。それ以外は trim して保持。
 * @param {string|null|undefined} value
 * @returns {string|null}
 */
export function normalizeRoadCondition(value) {
  if (value === null || value === undefined || value === '') return null;
  const v = String(value).trim();
  if (v === '----') return null;
  return v;
}
