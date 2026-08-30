export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8765/api';

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

export type ParamValue = string | number | boolean | undefined | null | Array<string | number>;
export type Params = Record<string, ParamValue>;

interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Params;
  signal?: AbortSignal;
  /** 跳过 GET 缓存/去重（用于轮询、实时数据接口） */
  noCache?: boolean;
}

// ---- GET 缓存 + in-flight 去重 ----
// 只缓存/合并 GET（幂等、无副作用）。30s TTL 内同一 URL 复用结果；
// 并发同 URL 请求共享同一 Promise（去重）。失败的结果立即从缓存移除。
const GET_CACHE_TTL = 30_000;
const getCache = new Map<string, { ts: number; promise: Promise<unknown> }>();
const GET_RETRIES = 2;

function buildUrl(path: string, params?: Params): string {
  let url = `${BASE_URL}${path}`;
  if (params) {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null) continue;
      if (Array.isArray(value)) {
        for (const v of value) search.append(key, String(v));
      } else {
        search.append(key, String(value));
      }
    }
    const qs = search.toString();
    if (qs) url += `?${qs}`;
  }
  return url;
}

async function performFetch<T>(
  url: string,
  method: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  if (!res.ok) {
    let errorBody: unknown;
    try {
      errorBody = await res.json();
    } catch {
      errorBody = await res.text().catch(() => '');
    }
    throw new ApiError(`API ${method} ${url} failed: ${res.status}`, res.status, errorBody);
  }

  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

function getWithCache<T>(url: string): Promise<T> {
  const hit = getCache.get(url);
  if (hit && Date.now() - hit.ts < GET_CACHE_TTL) {
    return hit.promise as Promise<T>;
  }

  // 带重试的请求（只重试网络错误，HTTP 错误直接抛）
  const promise = (async () => {
    let lastErr: unknown;
    for (let attempt = 0; attempt <= GET_RETRIES; attempt++) {
      try {
        return await performFetch<T>(url, 'GET');
      } catch (e) {
        if (e instanceof ApiError || attempt === GET_RETRIES) throw e;
        lastErr = e;
        // 指数退避：300ms → 600ms
        await new Promise((r) => setTimeout(r, 300 * (attempt + 1)));
      }
    }
    throw lastErr;
  })();

  getCache.set(url, { ts: Date.now(), promise });
  // 失败即失效（不允许缓存 rejection）
  promise.catch(() => {
    if (getCache.get(url)?.promise === promise) getCache.delete(url);
  });
  return promise;
}

// 定期清理过期缓存项，避免 Map 无限增长
setInterval(() => {
  const now = Date.now();
  for (const [k, v] of getCache) {
    if (now - v.ts > GET_CACHE_TTL) getCache.delete(k);
  }
}, 60_000);

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, params, signal, noCache } = options;
  const url = buildUrl(path, params);

  // GET + 可取消信号：走缓存/去重/重试；带 signal 或 noCache 的（可取消/实时）不缓存
  if (method === 'GET' && !signal && !noCache) {
    return getWithCache<T>(url);
  }
  return performFetch<T>(url, method, body, signal);
}

export const client = {
  get: <T>(path: string, params?: Params, signal?: AbortSignal, noCache?: boolean) =>
    request<T>(path, { method: 'GET', params, signal, noCache }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  put: <T>(path: string, body?: unknown, params?: Params) => request<T>(path, { method: 'PUT', body, params }),
  delete: <T>(path: string, params?: Params) => request<T>(path, { method: 'DELETE', params })
};
