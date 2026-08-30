// 全局导航节点状态：Sidebar 写入，媒体页读取并据此筛选。
// 用于解耦 AppShell 中的 Sidebar 与主内容区中的媒体页。

export type NavType =
  | 'all'
  | 'library'
  | 'tag'
  | 'continue'
  | 'recent'
  | 'favorite'
  | 'smartfolder';

export interface NavNode {
  type: NavType;
  value: string;
  label: string;
}

class NavigationStore {
  current = $state<NavNode>({ type: 'all', value: 'all', label: '全部媒体' });
  /** 用户点击侧边栏的计数（每次 set 自增）。媒体页用它区分"用户操作"与
   *  初始默认值——点击侧边栏时应自动切到媒体库视图，即使导航节点本身没变。 */
  navigateCount = $state(0);

  set(node: NavNode): void {
    this.current = node;
    this.navigateCount++;
  }

  reset(): void {
    this.current = { type: 'all', value: 'all', label: '全部媒体' };
  }

  isActive(node: { type: NavType; value: string }): boolean {
    return this.current.type === node.type && this.current.value === node.value;
  }
}

export const navigation = new NavigationStore();
