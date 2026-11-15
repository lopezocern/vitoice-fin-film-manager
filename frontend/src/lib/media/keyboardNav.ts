/**
 * 资产表格的键盘导航规则（纯函数，便于单测）。
 *
 * 为什么单独抽出来：这些判断是"输入行为"而不是"渲染"，放在组件里既没法测，
 * 也容易在改动模板时悄悄失效。表格只负责 `keydown → resolveNavKey() → 动作`。
 */

export type NavAction = 'next' | 'prev' | 'toggle' | 'toggleAll' | 'open' | 'edit' | 'ignore' | 'none';

export interface NavKeyEvent {
  key: string;
  metaKey?: boolean;
  ctrlKey?: boolean;
  altKey?: boolean;
}

/**
 * 按键 → 动作。
 *
 * - `j` / `↓`：下一条；`k` / `↑`：上一条
 * - `空格`：切换当前行选中
 * - `x`：选中/取消本页全部
 * - `Enter`：打开详情；`e`：编辑；`i`：忽略/恢复刮削
 *
 * 带 Ctrl/Cmd/Alt 的组合键一律不处理——那些是浏览器/系统的快捷键。
 */
export function resolveNavKey(e: NavKeyEvent): NavAction {
  if (e.metaKey || e.ctrlKey || e.altKey) return 'none';
  switch (e.key) {
    case 'j':
    case 'ArrowDown':
      return 'next';
    case 'k':
    case 'ArrowUp':
      return 'prev';
    case ' ':
    case 'Spacebar':
      return 'toggle';
    case 'x':
    case 'X':
      return 'toggleAll';
    case 'Enter':
      return 'open';
    case 'e':
    case 'E':
      return 'edit';
    case 'i':
    case 'I':
      return 'ignore';
    default:
      return 'none';
  }
}

/**
 * 光标移动。空列表返回 -1；首尾不环绕（继续按 j 停在最后一行，
 * 比"从末尾跳回开头"更符合表格类界面的预期）。
 */
export function moveCursor(current: number, delta: number, length: number): number {
  if (length <= 0) return -1;
  if (current < 0) return delta > 0 ? 0 : length - 1;
  const next = current + delta;
  if (next < 0) return 0;
  if (next >= length) return length - 1;
  return next;
}

/**
 * 焦点是否在可编辑控件里——是的话必须让按键走原生行为。
 *
 * 否则在搜索框里打 "j" 会顺手把选中项切走，这是最招人烦的一类 bug。
 */
export function isEditableTarget(el: { tagName?: string; isContentEditable?: boolean } | null): boolean {
  if (!el) return false;
  if (el.isContentEditable) return true;
  const tag = (el.tagName ?? '').toUpperCase();
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
}
