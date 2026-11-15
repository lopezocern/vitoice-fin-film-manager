import { describe, it, expect } from 'vitest';
import { filterTreeByType, flattenTags, type Tag } from './tags';

function tag(id: string, tagTypeId: number | undefined, children?: Tag[]): Tag {
  return { id, name: id, tag_type_id: tagTypeId, created_at: '', children } as Tag;
}

/**
 * `filterTreeByType` 原先住在 `lib/manage/filters.ts`（PR6 已删除），测试随之搬来。
 * 语义：命中节点保留整棵子树；未命中节点丢掉、但把命中的后代提上来。
 * 资产工作台的标签筛选依赖它——对层级列表做扁平 filter 会漏掉挂在
 * 其它类型父节点下的标签。
 */
describe('filterTreeByType', () => {
  it('keeps a matching node with its whole sub-tree', () => {
    const tree = [tag('a', 1, [tag('a1', 2), tag('a2', 9)])];
    expect(filterTreeByType(tree, 1).map((t) => t.id)).toEqual(['a']);
  });

  it('promotes matching descendants of a non-matching node', () => {
    const tree = [tag('a', 1, [tag('a1', 2), tag('b1', 3)])];
    expect(filterTreeByType(tree, 3).map((t) => t.id)).toEqual(['b1']);
  });

  it('drops sub-trees with no match', () => {
    const tree = [tag('a', 1, [tag('a1', 2)]), tag('b', 4)];
    expect(filterTreeByType(tree, 4).map((t) => t.id)).toEqual(['b']);
  });

  it('returns an empty list when nothing matches', () => {
    expect(filterTreeByType([tag('a', 1), tag('b', 1)], 7)).toEqual([]);
  });
});

describe('flattenTags', () => {
  it('walks depth-first and keeps order', () => {
    const tree = [tag('a', 1, [tag('a1', 1), tag('a2', 1)]), tag('b', 1)];
    expect(flattenTags(tree).map((t) => t.id)).toEqual(['a', 'a1', 'a2', 'b']);
  });

  it('handles a flat list and empty children', () => {
    expect(flattenTags([tag('x', 1, [])]).map((t) => t.id)).toEqual(['x']);
    expect(flattenTags([])).toEqual([]);
  });
});
