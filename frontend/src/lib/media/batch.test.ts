import { describe, it, expect } from 'vitest';
import { BATCH_CHUNK_SIZE, batchCount, chunkIds } from './batch';

describe('chunkIds', () => {
  it('keeps a small list in one chunk', () => {
    expect(chunkIds([1, 2, 3], 1000)).toEqual([[1, 2, 3]]);
  });

  it('splits on the exact multiple without an empty tail', () => {
    // 2000 = 1000 + 1000：不能出现第 3 个空分片（否则会发出一次空请求）
    expect(chunkIds([1, 2, 3, 4], 2)).toEqual([
      [1, 2],
      [3, 4]
    ]);
  });

  it('puts the remainder in a final shorter chunk', () => {
    expect(chunkIds([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]]);
  });

  it('returns no chunks for an empty selection', () => {
    expect(chunkIds([], 1000)).toEqual([]);
    expect(batchCount([], 1000)).toBe(0);
  });

  it('preserves order — batch actions are order-sensitive for `rename` start_index', () => {
    const ids = Array.from({ length: 2500 }, (_, i) => i + 1);
    const flat = chunkIds(ids).flat();
    expect(flat).toEqual(ids);
  });

  it('defaults to the backend limit', () => {
    expect(BATCH_CHUNK_SIZE).toBe(1000);
    expect(chunkIds(Array.from({ length: 2500 }, (_, i) => i))).toHaveLength(3);
    expect(batchCount(Array.from({ length: 2500 }, (_, i) => i))).toBe(3);
  });

  it('degrades safely for a non-positive size instead of looping forever', () => {
    expect(chunkIds([1, 2, 3], 0)).toEqual([[1, 2, 3]]);
    expect(chunkIds([1, 2, 3], -5)).toEqual([[1, 2, 3]]);
  });
});
