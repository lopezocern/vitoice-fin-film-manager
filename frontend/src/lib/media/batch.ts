/**
 * 批量操作的分片工具。
 *
 * 后端 `POST /media/batch` 的 `media_ids` 有 `max_length=1000` 上限（Pydantic 校验，
 * 超了直接 422）。跨页全选后一次可能选中几千条，必须切片提交。
 *
 * 抽成纯函数是为了能单测——组件里的 `for` 循环没法直接验证边界
 * （正好整除、余数、空数组、单条超限）。
 */

/** 与后端 `BatchActionRequest.media_ids` 的 max_length 保持一致。 */
export const BATCH_CHUNK_SIZE = 1000;

/** 把 id 列表按 `size` 切成连续分片；`size <= 0` 时退化为单片。 */
export function chunkIds(ids: readonly number[], size: number = BATCH_CHUNK_SIZE): number[][] {
  if (ids.length === 0) return [];
  const step = Number.isFinite(size) && size > 0 ? Math.floor(size) : ids.length;
  const chunks: number[][] = [];
  for (let i = 0; i < ids.length; i += step) {
    chunks.push(ids.slice(i, i + step));
  }
  return chunks;
}

/** 分片数（用于"将分 N 批提交"的提示）。 */
export function batchCount(ids: readonly number[], size: number = BATCH_CHUNK_SIZE): number {
  return chunkIds(ids, size).length;
}
