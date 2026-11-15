/**
 * 目录树变更版本号。
 *
 * `DirectoryTree` 把展开/子节点缓存在组件内部 state 里，目录被增删改名后
 * 缓存会过期。用一个自增版本号把它 `{#key}` 重新挂载，比给组件加
 * "强制刷新" 接口侵入性更小。
 */
let revision = $state(0);

export const folderTree = {
  get revision(): number {
    return revision;
  },
  bump(): void {
    revision++;
  }
};
