/**
 * Safe extraction of human-readable text from an unknown thrown value.
 *
 * `catch (e)` binds `unknown` under `useUnknownInCatchVariables`, so reaching
 * into `e.body` / `e.message` requires a guard. The API layer throws
 * `ApiError` whose `body` carries the backend's `detail` string; everything
 * else (a `TypeError` from a bug, a bare thrown string, an aborted fetch)
 * falls back to `Error.message` and then to the caller's fallback.
 */

type UnknownRecord = Record<string, unknown>;

function asRecord(value: unknown): UnknownRecord | null {
  return typeof value === 'object' && value !== null ? (value as UnknownRecord) : null;
}

function asNonEmptyString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

/**
 * Best-effort message for a caught value.
 *
 * Handles FastAPI's two `detail` shapes: a plain string (HTTPException) and a
 * validation array (422) — the latter carries no single usable sentence, so it
 * is skipped rather than stringified into "[object Object]".
 */
export function errorMessage(e: unknown, fallback = '操作失败'): string {
  const record = asRecord(e);

  if (record) {
    const body = asRecord(record.body);
    if (body) {
      const detail = asNonEmptyString(body.detail);
      if (detail) return detail;
    }
    const message = asNonEmptyString(record.message);
    if (message) return message;
  }

  const direct = asNonEmptyString(e);
  return direct ?? fallback;
}

/** HTTP status when the value is an `ApiError`; `null` for anything else. */
export function errorStatus(e: unknown): number | null {
  const record = asRecord(e);
  if (record && typeof record.status === 'number') return record.status;
  return null;
}

/** True when the request was aborted by an `AbortController` signal. */
export function isAbortError(e: unknown): boolean {
  const record = asRecord(e);
  return !!record && record.name === 'AbortError';
}
