import { describe, it, expect } from 'vitest';
import {
  ASSET_COLUMNS,
  ASSET_GRID_TEMPLATE,
  HIDEABLE_COLUMNS,
  gridTemplate,
  visibleColumns
} from './columns';

describe('visibleColumns', () => {
  it('shows every column by default', () => {
    expect(visibleColumns(ASSET_COLUMNS, [])).toHaveLength(ASSET_COLUMNS.length);
  });

  it('drops hidden columns', () => {
    const cols = visibleColumns(ASSET_COLUMNS, ['tags', 'library']);
    expect(cols.map((c) => c.id)).not.toContain('tags');
    expect(cols.map((c) => c.id)).not.toContain('library');
    expect(cols).toHaveLength(ASSET_COLUMNS.length - 2);
  });

  it('never hides asset or actions — otherwise a row has no title and no buttons', () => {
    const cols = visibleColumns(ASSET_COLUMNS, ['asset', 'actions']);
    const ids = cols.map((c) => c.id);
    expect(ids).toContain('asset');
    expect(ids).toContain('actions');
  });

  it('ignores unknown ids from stale localStorage', () => {
    // 旧版本存下来的列名不该让表格变空或抛错
    const cols = visibleColumns(ASSET_COLUMNS, ['removed_column', 'ghost']);
    expect(cols).toHaveLength(ASSET_COLUMNS.length);
  });

  it('can hide every hideable column at once and still keep the table usable', () => {
    const cols = visibleColumns(
      ASSET_COLUMNS,
      HIDEABLE_COLUMNS.map((c) => c.id)
    );
    expect(cols.map((c) => c.id)).toEqual(['asset', 'actions']);
  });
});

describe('gridTemplate', () => {
  // 注意：轨道值本身含空格（`minmax(220px, 1.6fr)`），所以不能按空格数轨道。
  // 真正要防的 bug 是"模板来自默认列、单元格来自可见列"导致的错位。
  it('is built from the given columns, not from the global default', () => {
    const cols = visibleColumns(ASSET_COLUMNS, ['size', 'rating']);
    const expected = cols.map((c) => c.track).join(' ');
    expect(gridTemplate(cols)).toBe(expected);
    expect(gridTemplate(cols)).not.toBe(ASSET_GRID_TEMPLATE);
  });

  it('default template matches the full column list', () => {
    expect(ASSET_GRID_TEMPLATE).toBe(ASSET_COLUMNS.map((c) => c.track).join(' '));
  });

  it('keeps track order stable after hiding a middle column', () => {
    const cols = visibleColumns(ASSET_COLUMNS, ['library']);
    const tpl = gridTemplate(cols);
    // 隐藏后 asset 仍是第一轨、actions 仍是最后一轨
    expect(tpl.startsWith('minmax(220px, 1.6fr)')).toBe(true);
    expect(tpl.endsWith('158px')).toBe(true);
    // 被隐藏列的轨道确实不在了
    expect(tpl).not.toContain('minmax(110px, 0.7fr)');
  });
});

describe('HIDEABLE_COLUMNS', () => {
  it('excludes the two fixed columns', () => {
    const ids = HIDEABLE_COLUMNS.map((c) => c.id);
    expect(ids).not.toContain('asset');
    expect(ids).not.toContain('actions');
    expect(ids.length).toBe(ASSET_COLUMNS.length - 2);
  });
});
