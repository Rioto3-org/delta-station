// imported=TRUEの行を削除対象として抽出する（GAS/Node非依存の純粋関数）。
//
// 行番号の降順で返す: sheet.deleteRow()は削除位置より下の行番号を1つずつ詰める
// ため、大きい番号から処理すれば、まだ処理していない対象行の番号は
// 削除の影響を受けず安定する（小さい番号から消すと後続の番号がずれる）。

/**
 * @param {{rowNumber: number, imported: boolean, imageDriveId?: string}[]} rows
 * @returns {{rowNumber: number, imageDriveId?: string}[]} 行番号降順
 */
export function selectRowsToCleanup(rows) {
  return rows
    .filter((r) => r.imported === true)
    .sort((a, b) => b.rowNumber - a.rowNumber);
}
