import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseHtml, resolveUrl } from '../src/core/parse.js';

// fixtures/delta_sample.html は実ページを Shift_JIS の生バイトで保存したもの。
// アダプタと同じく TextDecoder('shift_jis') で復号してからパースする（復号+パースの結合テスト）。
const fixturePath = fileURLToPath(new URL('../fixtures/delta_sample.html', import.meta.url));
const html = new TextDecoder('shift_jis').decode(readFileSync(fixturePath));
const SRC = 'http://www2.thr.mlit.go.jp/sendai/html/DR-74125.html';

describe('parseHtml（実HTMLフィクスチャ）', () => {
  const raw = parseHtml(html, SRC);

  it('観測日時', () => expect(raw.observed_at).toBe('2026-07-27 21:50'));
  it('撮影日時（年補完）', () => expect(raw.captured_at).toBe('2026-07-27 21:52'));
  it('観測地点名', () => expect(raw.location_name).toBe('作並宿'));
  it('住所', () => expect(raw.location_address).toBe('仙台市青葉区作並字神前西'));
  it('累加雨量（生値）', () => expect(raw.cumulative_rainfall).toBe('0mm'));
  it('気温（生値）', () => expect(raw.temperature).toBe('19.6℃'));
  it('風速（生値）', () => expect(raw.wind_speed).toBe('0.4m/s'));
  it('路面温度（生値）', () => expect(raw.road_temperature).toBe('20.1℃'));
  it('路面状況（生値）', () => expect(raw.road_condition).toBe('----'));
  it('画像URL（絶対化）', () =>
    expect(raw.image_url).toBe('http://www2.thr.mlit.go.jp/sendai/html/image/DR-74125-l.jpg'));
});

describe('resolveUrl', () => {
  it('相対パスをベースのディレクトリに解決', () => {
    expect(resolveUrl('http://h/sendai/html/DR-74125.html', 'image/a.jpg'))
      .toBe('http://h/sendai/html/image/a.jpg');
  });
  it('絶対URLはそのまま', () => {
    expect(resolveUrl('http://h/x/y.html', 'http://other/z.jpg')).toBe('http://other/z.jpg');
  });
  it('ルート相対', () => {
    expect(resolveUrl('http://h/x/y.html', '/z.jpg')).toBe('http://h/z.jpg');
  });
});
