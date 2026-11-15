/**
 * 列显示偏好（哪些列被隐藏）。
 *
 * 与列宽分开存：宽度是"微调"，可见性是"配置"，重置语义不同
 * （表格里双击表头只重置宽度）。
 *
 * 用共享 store 而不是把状态塞进 AssetsTable：工具栏要渲染「列」菜单，
 * 表格要根据同一份状态计算 grid 模板与单元格，两处必须读同一个源。
 */
import { HIDEABLE_COLUMNS, type AssetColumnId } from './columns';

const HIDDEN_KEY = 'vitoice.assets.hiddencols';

/** 不可隐藏的列不允许进入集合（防止旧配置/手改 localStorage 把表搞空）。 */
const HIDEABLE_IDS = new Set<string>(HIDEABLE_COLUMNS.map((c) => c.id));

function read(): Set<string> {
  if (typeof localStorage === 'undefined') return new Set();
  try {
    const raw = localStorage.getItem(HIDDEN_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return new Set();
    // 未知 id 与不可隐藏列一律丢弃：旧版本列名变更后不至于渲染成空表
    return new Set(
      parsed.filter((id): id is string => typeof id === 'string' && HIDEABLE_IDS.has(id))
    );
  } catch {
    return new Set();
  }
}

function write(hidden: Set<string>): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(HIDDEN_KEY, JSON.stringify([...hidden]));
  } catch {
    // 配额/隐私模式：偏好丢一次不影响使用
  }
}

let hidden = $state<Set<string>>(read());

export const columnPrefs = {
  get hidden(): Set<string> {
    return hidden;
  },
  isVisible(id: AssetColumnId): boolean {
    return !HIDEABLE_IDS.has(id) || !hidden.has(id);
  },
  toggle(id: AssetColumnId): void {
    if (!HIDEABLE_IDS.has(id)) return;
    const next = new Set(hidden);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    hidden = next;
    write(next);
  },
  reset(): void {
    hidden = new Set();
    write(hidden);
  }
};
