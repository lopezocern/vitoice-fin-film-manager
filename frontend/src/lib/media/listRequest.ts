/**
 * 列表请求的超时与重试策略（纯逻辑，便于单测）。
 *
 * 背景：`createMediaList` 原来直接 `await mediaApi.list()`。
 * 后端卡住（DB 锁、磁盘扫描占满 IO）时前端会一直转圈，用户只能刷新整页；
 * 偶发的一次网络抖动也会让列表直接变空并显示错误。
 *
 * 策略：
 * - 单次请求超时 15s，超时按"可重试错误"处理；
 * - 只对**幂等 GET** 自动重试一次（间隔 600ms），避免把慢当成失败反复打；
 * - 4xx 不重试（参数错了重试也不会变对）；
 * - 用户主动取消（AbortError）既不重试也不报错。
 */

export const LIST_TIMEOUT_MS = 15_000;
export const LIST_RETRY_DELAY_MS = 600;
/** 最多尝试次数（含首次）。 */
export const LIST_MAX_ATTEMPTS = 2;

export interface RetryableError {
  name?: string;
  status?: number | null;
}

/** 该错误值得再试一次吗？ */
export function shouldRetry(error: unknown, attempt: number): boolean {
  if (attempt >= LIST_MAX_ATTEMPTS) return false;
  const e = error as RetryableError | null | undefined;
  if (!e) return true;
  // 主动取消：不重试
  if (e.name === 'AbortError') return false;
  // 4xx（参数/权限/不存在）：重试没有意义
  if (typeof e.status === 'number' && e.status >= 400 && e.status < 500) return false;
  // 5xx 与网络错误：可以重试
  return true;
}

/** 超时错误标记，便于上层区分"超时"与"用户取消"。 */
export function timeoutError(): Error {
  const err = new Error(`请求超时（超过 ${Math.round(LIST_TIMEOUT_MS / 1000)} 秒）`);
  err.name = 'TimeoutError';
  return err;
}

/** 组合「外部取消信号」与「超时」：任一方触发都会中断请求。 */
export function withTimeout(
  timeoutMs: number = LIST_TIMEOUT_MS,
  external?: AbortSignal
): { signal: AbortSignal; cleanup: () => void; timedOut: () => boolean } {
  const controller = new AbortController();
  let didTimeout = false;
  const timer = setTimeout(() => {
    didTimeout = true;
    controller.abort();
  }, timeoutMs);
  const onExternalAbort = (): void => controller.abort();
  external?.addEventListener('abort', onExternalAbort, { once: true });

  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer);
      external?.removeEventListener('abort', onExternalAbort);
    },
    timedOut: () => didTimeout
  };
}

export function delay(ms: number = LIST_RETRY_DELAY_MS): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
