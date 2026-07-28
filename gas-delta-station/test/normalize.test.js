import { describe, it, expect } from 'vitest';
import { normalizeNumeric, normalizeRoadCondition } from '../src/core/normalize.js';
import { buildImageFilename } from '../src/core/filename.js';
import { buildObservation } from '../src/core/observation.js';

// Python側 models.py のテストケースと同じ値で突き合わせる。

describe('normalizeNumeric', () => {
  it('気温文字列から数値抽出 "4.7℃" -> 4.7', () => expect(normalizeNumeric('4.7℃')).toBe(4.7));
  it('風速 "1.9m/s" -> 1.9', () => expect(normalizeNumeric('1.9m/s')).toBe(1.9));
  it('累加雨量 "0mm" -> 0（負値許容せず）', () =>
    expect(normalizeNumeric('0mm', { allowNegative: false })).toBe(0));
  it('負の気温 "-5.0℃" -> -5', () => expect(normalizeNumeric('-5.0℃')).toBe(-5));
  it('欠損 "----" -> null', () => expect(normalizeNumeric('----')).toBeNull());
  it('空文字 -> null', () => expect(normalizeNumeric('')).toBeNull());
  it('null -> null', () => expect(normalizeNumeric(null)).toBeNull());
});

describe('normalizeRoadCondition', () => {
  it('"----" は null', () => expect(normalizeRoadCondition('----')).toBeNull());
  it('任意文字列は保持', () => expect(normalizeRoadCondition('積雪あり')).toBe('積雪あり'));
  it('前後空白は除去', () => expect(normalizeRoadCondition(' 湿潤 ')).toBe('湿潤'));
});

describe('buildImageFilename', () => {
  it('observed_at からファイル名生成', () => {
    expect(buildImageFilename('2026-02-16 10:50', 'http://x/image/DR-74125-l.jpg'))
      .toBe('20260216_1050_DR-74125-l.jpg');
  });
});

describe('buildObservation', () => {
  const raw = {
    observed_at: '2026-02-16 10:50',
    captured_at: '2026-02-16 10:52',
    cumulative_rainfall: '0mm',
    temperature: '4.7℃',
    wind_speed: '1.9m/s',
    road_temperature: '8.0℃',
    road_condition: '----',
    image_url: 'http://www2.thr.mlit.go.jp/sendai/html/image/DR-74125-l.jpg',
  };

  it('正常系（models.py の例と一致）', () => {
    const o = buildObservation(raw, 1);
    expect(o).toMatchObject({
      location_id: 1,
      observed_at: '2026-02-16 10:50',
      captured_at: '2026-02-16 10:52',
      cumulative_rainfall: 0,
      temperature: 4.7,
      wind_speed: 1.9,
      road_temperature: 8.0,
      road_condition: null,
      image_filename: '20260216_1050_DR-74125-l.jpg',
    });
  });

  it('範囲外の気温(999)は例外', () => {
    expect(() => buildObservation({ ...raw, temperature: '999℃' }, 1)).toThrow();
  });

  it('日時形式が不正なら例外', () => {
    expect(() => buildObservation({ ...raw, observed_at: '2026/02/16 10:50' }, 1)).toThrow();
  });

  it('実在しない日付(2月30日)は例外', () => {
    expect(() => buildObservation({ ...raw, observed_at: '2026-02-30 10:50' }, 1)).toThrow();
  });

  it('実在する閏日(2028-02-29)は許可', () => {
    const o = buildObservation({ ...raw, observed_at: '2028-02-29 10:50' }, 1);
    expect(o.observed_at).toBe('2028-02-29 10:50');
  });
});
