// 浏览队列：记录媒体页当前展示顺序下的媒体（id + 标题），供详情页 / 播放器做「上一个 / 下一个」。
//
// 与 mediaScroll 的区别：mediaScroll 是"返回时恢复滚动位置"的一次性快照，恢复完即清空；
// 本 store 是持续存在的浏览上下文——进入详情/播放器后仍然保留，用来做相邻内容切换。
//
// 用 module 级 $state：store 单例跨路由保留（+page 组件每次进入会重建，放组件内会丢）。
// 导出为对象而非裸 $state——组件里 import 的裸 rune 是只读的，改属性才合法。
export interface QueueItem {
  id: string;
  title: string;
}

export const mediaQueue = $state({
  items: [] as QueueItem[]
});

export interface QueueNeighbors {
  /** 当前项在队列中的下标；-1 表示不在队列中（如直接深链进入详情页） */
  index: number;
  prev: QueueItem | null;
  next: QueueItem | null;
  size: number;
}

/** 取当前媒体在浏览队列中的相邻项。不在队列中时 prev/next 均为 null。 */
export function queueNeighbors(currentId: string | number | null | undefined): QueueNeighbors {
  const size = mediaQueue.items.length;
  const miss: QueueNeighbors = { index: -1, prev: null, next: null, size };
  if (currentId == null) return miss;
  const index = mediaQueue.items.findIndex((it) => it.id === String(currentId));
  if (index < 0) return miss;
  return {
    index,
    prev: index > 0 ? mediaQueue.items[index - 1] : null,
    next: index < size - 1 ? mediaQueue.items[index + 1] : null,
    size
  };
}