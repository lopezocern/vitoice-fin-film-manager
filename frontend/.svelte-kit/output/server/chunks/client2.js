const BASE_URL = "http://127.0.0.1:8765/api";
class ApiError extends Error {
  status;
  body;
  constructor(message, status, body) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}
const GET_CACHE_TTL = 3e4;
const getCache = /* @__PURE__ */ new Map();
const GET_RETRIES = 2;
function buildUrl(path, params) {
  let url = `${BASE_URL}${path}`;
  if (params) {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value === void 0 || value === null) continue;
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
async function performFetch(url, method, body, signal) {
  const headers = {};
  if (body !== void 0) headers["Content-Type"] = "application/json";
  const res = await fetch(url, {
    method,
    headers,
    body: body !== void 0 ? JSON.stringify(body) : void 0,
    signal
  });
  if (!res.ok) {
    let errorBody;
    try {
      errorBody = await res.json();
    } catch {
      errorBody = await res.text().catch(() => "");
    }
    throw new ApiError(`API ${method} ${url} failed: ${res.status}`, res.status, errorBody);
  }
  if (res.status === 204) return void 0;
  const text = await res.text();
  if (!text) return void 0;
  return JSON.parse(text);
}
function getWithCache(url) {
  const hit = getCache.get(url);
  if (hit && Date.now() - hit.ts < GET_CACHE_TTL) {
    return hit.promise;
  }
  const promise = (async () => {
    let lastErr;
    for (let attempt = 0; attempt <= GET_RETRIES; attempt++) {
      try {
        return await performFetch(url, "GET");
      } catch (e) {
        if (e instanceof ApiError || attempt === GET_RETRIES) throw e;
        lastErr = e;
        await new Promise((r) => setTimeout(r, 300 * (attempt + 1)));
      }
    }
    throw lastErr;
  })();
  getCache.set(url, { ts: Date.now(), promise });
  promise.catch(() => {
    if (getCache.get(url)?.promise === promise) getCache.delete(url);
  });
  return promise;
}
setInterval(() => {
  const now = Date.now();
  for (const [k, v] of getCache) {
    if (now - v.ts > GET_CACHE_TTL) getCache.delete(k);
  }
}, 6e4);
async function request(path, options = {}) {
  const { method = "GET", body, params, signal, noCache } = options;
  const url = buildUrl(path, params);
  if (method === "GET" && !signal && !noCache) {
    return getWithCache(url);
  }
  return performFetch(url, method, body, signal);
}
const client = {
  get: (path, params, signal, noCache) => request(path, { method: "GET", params, signal, noCache }),
  post: (path, body) => request(path, { method: "POST", body }),
  put: (path, body, params) => request(path, { method: "PUT", body, params }),
  delete: (path, params) => request(path, { method: "DELETE", params })
};
export {
  ApiError as A,
  BASE_URL as B,
  client as c
};
