/**
 * 虚拟滚动窗口计算（纯函数）。
 *
 * 为什么单独抽出来：窗口算法是"边界最容易错"的一类代码——头部宽度、overscan、
 * 末尾 clamp 三处任一处差一都会表现为"滚到底少一行"或"向上滚不动"。
 * 放在组件里既测不了，也不好 review。
 *
 * 适用边界（重要）：本项目的表格是**服务端分页**（每页 ≤200 行），所以窗口算法
 * 正常不会触发（行数 ≤ 阈值）。它存在的意义是：
 *   1. page_size 提到 200 且阈值下调时直接生效；
 *   2. 网格/时间轴这类"一次加载全部"的视图将来复用同一套逻辑时不必重写；
 *   3. 数据量策略若改成"游标分页 + 累积"，行数会真的到几千。
 */

export interface VirtualWindowInput {
  /** 滚动容器当前 scrollTop */
  scrollTop: number;
  /** 表头高度：吸顶表头占了容器可视区顶部，行窗口要减去它 */
  headHeight: number;
  /** 滚动容器可视高度 */
  viewportHeight: number;
  /** 固定行高（必须与 CSS 一致） */
  rowHeight: number;
  /** 总行数 */
  total: number;
  /** 上下各多渲染几行，避免快速滚动出现空白 */
  overscan?: number;
}

export interface VirtualWindow {
  start: number;
  end: number;
  /** 上方未渲染行占位高度 */
  padTop: number;
  /** 下方未渲染行占位高度 */
  padBottom: number;
}

export function computeWindow(input: VirtualWindowInput): VirtualWindow {
  const { scrollTop, headHeight, viewportHeight, rowHeight, total } = input;
  const overscan = Math.max(0, input.overscan ?? 6);

  if (total <= 0 || rowHeight <= 0) {
    return { start: 0, end: 0, padTop: 0, padBottom: 0 };
  }

  // 第一行可见索引：滚动量减去吸顶表头，再除以行高
  const rawFirst = (scrollTop - headHeight) / rowHeight;
  const first = Math.max(0, Math.floor(rawFirst));
  const visible = Math.ceil(Math.max(0, viewportHeight) / rowHeight) + 2;

  const start = Math.max(0, Math.min(first - overscan, Math.max(0, total - 1)));
  const end = Math.min(total, first + visible + overscan);

  return {
    start,
    end: Math.max(start, end),
    padTop: start * rowHeight,
    padBottom: Math.max(0, (total - Math.max(start, end)) * rowHeight)
  };
}
