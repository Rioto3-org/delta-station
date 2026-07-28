import { describe, it, expect } from 'vitest';
import { selectRowsToCleanup } from '../src/core/cleanup.js';

describe('selectRowsToCleanup', () => {
  it('imported=TRUEの行だけを抽出する', () => {
    const rows = [
      { rowNumber: 2, imported: true, imageDriveId: 'a' },
      { rowNumber: 3, imported: false, imageDriveId: 'b' },
      { rowNumber: 4, imported: true, imageDriveId: 'c' },
    ];
    const result = selectRowsToCleanup(rows);
    expect(result.map((r) => r.rowNumber)).toEqual([4, 2]);
  });

  it('行番号の降順で返す(削除時のインデックスずれ防止)', () => {
    const rows = [
      { rowNumber: 2, imported: true },
      { rowNumber: 10, imported: true },
      { rowNumber: 5, imported: true },
    ];
    const result = selectRowsToCleanup(rows);
    expect(result.map((r) => r.rowNumber)).toEqual([10, 5, 2]);
  });

  it('imported=TRUEが無ければ空配列', () => {
    const rows = [{ rowNumber: 2, imported: false }];
    expect(selectRowsToCleanup(rows)).toEqual([]);
  });

  it('imported以外のtruthy値(文字列等)は対象にしない(===trueのみ)', () => {
    const rows = [{ rowNumber: 2, imported: 'TRUE' }];
    expect(selectRowsToCleanup(rows)).toEqual([]);
  });
});
