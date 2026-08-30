import "clsx";
class NavigationStore {
  current = { type: "all", value: "all", label: "全部媒体" };
  /** 用户点击侧边栏的计数（每次 set 自增）。媒体页用它区分"用户操作"与
   *  初始默认值——点击侧边栏时应自动切到媒体库视图，即使导航节点本身没变。 */
  navigateCount = 0;
  set(node) {
    this.current = node;
    this.navigateCount++;
  }
  reset() {
    this.current = { type: "all", value: "all", label: "全部媒体" };
  }
  isActive(node) {
    return this.current.type === node.type && this.current.value === node.value;
  }
}
const navigation = new NavigationStore();
export {
  navigation as n
};
