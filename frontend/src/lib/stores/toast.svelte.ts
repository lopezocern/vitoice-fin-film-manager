/**
 * One toast queue for the whole app.
 *
 * Why: `showToast` was copy-pasted into 13 components, each with its own markup
 * and its own 3.2s timer. The new asset workspace needs it too, so this is the
 * shared one. Existing components are not migrated yet — they keep working.
 *
 * Supports an optional single action button (used for "撤销" on destructive
 * operations): the toast stays longer and the button runs a callback once.
 *
 * Tones: `ok` 成功、`err` 失败、`warn` 部分完成/被取消（不是错误，但需要看见）。
 */
export type ToastTone = 'ok' | 'err' | 'warn';

export interface ToastAction {
  label: string;
  run: () => void | Promise<void>;
}

export interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
  action?: ToastAction;
}

const DEFAULT_TTL_MS = 3600;
/** Actionable toasts (撤销) need a window the user can actually reach. */
const ACTION_TTL_MS = 10_000;

let seq = 0;
let items = $state<ToastItem[]>([]);

function dismiss(id: number): void {
  items = items.filter((t) => t.id !== id);
}

function push(
  message: string,
  tone: ToastTone = 'ok',
  options: { ttlMs?: number; action?: ToastAction } = {}
): number {
  const id = ++seq;
  const ttl = options.ttlMs ?? (options.action ? ACTION_TTL_MS : DEFAULT_TTL_MS);
  items = [...items, { id, message, tone, action: options.action }];
  if (ttl > 0) {
    setTimeout(() => dismiss(id), ttl);
  }
  return id;
}

/** Run a toast's action once, then drop the toast. */
async function runAction(id: number): Promise<void> {
  const item = items.find((t) => t.id === id);
  dismiss(id);
  try {
    await item?.action?.run();
  } catch {
    // 动作失败由调用方自己 push 错误提示；这里不再二次打扰
  }
}

export const toasts = {
  get items(): ToastItem[] {
    return items;
  },
  push,
  dismiss,
  runAction,
  clear(): void {
    items = [];
  }
};
