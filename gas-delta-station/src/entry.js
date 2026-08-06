// GASのエントリポイント。ここで export した関数を build.mjs がグローバル関数として露出させる。
// GASのトリガー/エディタからは main / cleanup / setupTrigger を直接呼ぶ。

import { runScrape } from './pipeline.js';
import { createGasAdapter, HEADER } from './adapters/gas.js';
import { CONFIG } from './core/config.js';
import { selectRowsToCleanup } from './core/cleanup.js';

function getImageFolderId() {
  const id = PropertiesService.getScriptProperties().getProperty('IMAGE_FOLDER_ID');
  if (!id) throw new Error('スクリプトプロパティ IMAGE_FOLDER_ID が未設定です');
  return id;
}

export function main() {
  const adapter = createGasAdapter({
    sheetName: CONFIG.sheetName,
    imageFolderId: getImageFolderId(),
  });
  const result = runScrape(adapter, CONFIG);
  console.log(`結果: ${result.status} (${result.observation.observed_at})`);
  return result.status;
}

const IMPORTED_COL_INDEX = HEADER.indexOf('imported');
const IMAGE_DRIVE_ID_COL_INDEX = HEADER.indexOf('image_drive_id');

// Drive APIをサービスアカウント(編集者)から呼ぶとオーナーでないため削除・trash不可
// (403 insufficientFilePermissions)。GASはファイル作成者=オーナー本人の権限で動くため、
// 削除はPython側ではなくここで行う。
function trashDriveFile(fileId) {
  if (!fileId) return true; // 対象なし=既に片付いているとみなす
  try {
    const file = DriveApp.getFileById(fileId);
    if (!file.isTrashed()) file.setTrashed(true);
    return true;
  } catch (e) {
    const msg = String((e && e.message) || e);
    if (/not found/i.test(msg)) return true; // 既に削除済み
    console.log(`画像削除失敗 (fileId=${fileId}): ${msg}`);
    return false;
  }
}

/**
 * Python側の取り込みバッチが imported=TRUE を立てた行を対象に、
 * Drive画像をゴミ箱へ、シート行を削除する。GAS側はあくまでキャッシュのため。
 * Drive削除に失敗した行はシート行を消さず、次回このcleanup実行時に再試行される。
 */
export function cleanup() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.sheetName);
  const lastRow = sheet ? sheet.getLastRow() : 0;
  if (lastRow < 2) {
    console.log('キャッシュ削除: 対象なし');
    return;
  }

  const values = sheet.getRange(2, 1, lastRow - 1, HEADER.length).getValues();
  const rows = values.map((row, i) => ({
    rowNumber: i + 2,
    imported: row[IMPORTED_COL_INDEX],
    imageDriveId: row[IMAGE_DRIVE_ID_COL_INDEX],
  }));

  const targets = selectRowsToCleanup(rows);
  let deleted = 0;
  targets.forEach(({ rowNumber, imageDriveId }) => {
    if (trashDriveFile(imageDriveId)) {
      sheet.deleteRow(rowNumber);
      deleted += 1;
    }
  });
  console.log(`キャッシュ削除: ${deleted}/${targets.length}行`);
}

export function setupTrigger() {
  ScriptApp.getProjectTriggers()
    .filter((t) => ['main', 'cleanup'].includes(t.getHandlerFunction()))
    .forEach((t) => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('main').timeBased().everyMinutes(15).create();
  ScriptApp.newTrigger('cleanup').timeBased().everyDays(1).atHour(3).create();
  console.log('15分間隔の取得トリガーと、1日1回のキャッシュ削除トリガーを設置しました');
}
