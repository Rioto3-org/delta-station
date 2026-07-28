// 画像ファイル名の生成（Python: ScrapedRawData.to_observation 内のロジック相当）

/**
 * observed_at と画像URLから保存ファイル名を生成。
 * 例: ("2026-02-16 10:50", ".../DR-74125-l.jpg") -> "20260216_1050_DR-74125-l.jpg"
 * @param {string} observedAt "YYYY-MM-DD HH:MM"
 * @param {string} imageUrl
 * @returns {string}
 */
export function buildImageFilename(observedAt, imageUrl) {
  const timestamp = observedAt.replace(/-/g, '').replace(/:/g, '').replace(/ /g, '_');
  const original = imageUrl.split('/').pop() || 'image.jpg';
  let base;
  let ext;
  if (original.includes('.')) {
    const i = original.lastIndexOf('.');
    base = original.slice(0, i);
    ext = original.slice(i + 1);
  } else {
    base = original;
    ext = 'jpg';
  }
  return `${timestamp}_${base}.${ext}`;
}
