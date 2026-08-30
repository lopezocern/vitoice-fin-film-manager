// 跨路由保留媒体列表滚动位置与页码。
// 媒体页进入详情/系列页时保存 .media-content 的 scrollTop 和当前页码；
// 返回后媒体数据异步加载完成时恢复，避免回到页面顶部或第 1 页。
// 用 module 级 $state：store 单例跨导航保留（+page 组件每次进入会重建，不能放组件内）。
// 导出为对象而非裸 $state——组件里 import 的裸 rune 是只读的，改属性才合法。
//
// 注意：页码必须走这里而不是 URL——SvelteKit dev 模式下 history.state 不存 URL，
// URL effect 用 replaceState 写入的 page 在 history.back() 返回时恢复不出来，
// 导致组件重建后 page 被初始化为 1（回到"上一页的开头"）。
//
// 快照恢复（桌面端）：返回时直接使用离开时的数据快照（savedItems/savedSeries），
// 不重新请求——列表数据与离开时完全一致，渲染/布局一致，滚动位置一步到位，
// 彻底避开"返回后重新请求 + 补页 + 增量渲染"的异步时序问题。
export const mediaScroll = $state({
  top: 0,
  page: 0,
  anchorId: '',
  anchorOffset: 0,
  savedItems: null as import('$lib/api/media').Media[] | null,
  savedSeries: null as import('$lib/api/series').Series[] | null,
});
