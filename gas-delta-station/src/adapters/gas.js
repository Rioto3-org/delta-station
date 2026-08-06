// GAS本番アダプタ。UrlFetchApp / SpreadsheetApp / DriveApp を使用。
// このファイルは GAS ランタイムでのみ動作する（Nodeのテストからは import しない）。

export const HEADER = [
  'observed_at', 'captured_at', 'cumulative_rainfall', 'temperature', 'wind_speed',
  'road_temperature', 'road_condition', 'image_filename', 'image_drive_id', 'image_url',
  'location_name', 'created_at', 'imported',
];

function ensureHeader(sheet) {
  if (sheet.getLastRow() === 0) sheet.appendRow(HEADER);
}

// observed_at/captured_at列（A:B）をプレーンテキスト書式に固定する。
// これをしないと "2026-07-28 06:12" のような日付っぽい文字列を appendRow で書いた際、
// Sheetsが自動的に日付型（シリアル値）へ変換してしまい、Python側でのパースが壊れる。
function ensureDatetimeColumnsAreText(sheet) {
  sheet.getRange('A:B').setNumberFormat('@');
}

export function createGasAdapter({ sheetName, imageFolderId }) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(sheetName) || ss.insertSheet(sheetName);
  ensureHeader(sheet);
  ensureDatetimeColumnsAreText(sheet);

  return {
    fetchText(url) {
      return UrlFetchApp.fetch(url, { muteHttpExceptions: false }).getContentText('Shift_JIS');
    },
    fetchBytes(url) {
      return UrlFetchApp.fetch(url).getBlob();
    },
    hasObservedAt(observedAt) {
      const last = sheet.getLastRow();
      if (last < 2) return false;
      const col = sheet.getRange(2, 1, last - 1, 1).getValues();
      // プレーンテキスト化前に書かれた行はDate型で返ってくるため、両対応で比較する
      return col.some((r) => {
        const v = r[0];
        const s = v instanceof Date
          ? Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm')
          : String(v);
        return s === observedAt;
      });
    },
    saveImage(filename, blob) {
      const folder = DriveApp.getFolderById(imageFolderId);
      const file = folder.createFile(blob.setName(filename));
      return file.getId();
    },
    appendObservation(row) {
      sheet.appendRow([
        row.observed_at, row.captured_at, row.cumulative_rainfall, row.temperature,
        row.wind_speed, row.road_temperature,
        row.road_condition === null ? '' : row.road_condition,
        row.image_filename, row.image_ref, row.image_url, row.location_name,
        new Date(), false,
      ]);
    },
    log(m) {
      console.log(m);
    },
  };
}
