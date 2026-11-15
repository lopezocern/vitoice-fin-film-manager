import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

/**
 * 旧管理页 URL → 新结构的重定向（PR4）。
 *
 * 为什么放在 `load` 而不是组件里：重定向必须发生在组件挂载**之前**，
 * 否则旧 section 会先渲染一帧旧组件再跳走。`load` 在客户端导航时同样执行，
 * 所以 URL 栏直接输入旧地址也能正确落地。
 *
 * 迁移表（其余参数 - lib/dir/tags/sort/order/page/q - 原样保留）：
 *   section=overview          → section=assets&view=all
 *   section=files             → section=assets&view=all
 *   section=files&source=missing  → section=assets&view=missing
 *   section=files&status=untagged → section=assets&view=untagged
 *   section=issues            → section=assets&view=problem
 *   section=metadata          → section=assets&view=metadata
 *   section=tasks             → section=runs&tab=tasks
 *   section=history           → section=runs&tab=history
 *   section=recycle / tab=recycle → section=trash
 *   tab=tags                  → section=tags
 *   tab=media                 → section=assets
 */

/** 旧 section → 新 section（`assets` 的视图另由 args 决定）。 */
const SECTION_ALIASES: Record<string, string> = {
  overview: 'assets',
  files: 'assets',
  assets: 'assets',
  issues: 'assets',
  metadata: 'assets',
  tasks: 'runs',
  history: 'runs',
  libraries: 'libraries',
  tags: 'tags',
  trash: 'trash',
  recycle: 'trash'
};

/** 旧 `section` 值直接决定资产工作台的视图。 */
const SECTION_TO_VIEW: Record<string, string> = {
  issues: 'problem',
  metadata: 'metadata'
};

/** 触发「清理一次性参数」的旧 section 集合。 */
const LEGACY_SECTIONS = new Set([
  'overview',
  'files',
  'issues',
  'metadata',
  'tasks',
  'history',
  'recycle'
]);

export const load: PageLoad = ({ url }) => {
  const params = url.searchParams;
  const rawSection = params.get('section');
  const rawTab = params.get('tab');

  // 没有 section 也没有旧 tab：交给页面默认（assets）
  if (!rawSection && !rawTab) return {};

  const target = new URL(url);
  const next = target.searchParams;
  let changed = false;

  // 1) tab= 旧参数（media/tags/recycle）→ section
  if (!rawSection && rawTab) {
    const section = rawTab === 'tags' ? 'tags' : rawTab === 'recycle' ? 'trash' : 'assets';
    next.set('section', section);
    next.delete('tab');
    changed = true;
  }

  // 2) section 别名
  const aliased = rawSection ? SECTION_ALIASES[rawSection] : undefined;
  if (rawSection && aliased && aliased !== rawSection) {
    next.set('section', aliased);
    changed = true;
  }

  const section = next.get('section');

  // 旧 section 隐含的视图 / tab
  if (section === 'assets' && rawSection && !next.get('view')) {
    const implied =
      SECTION_TO_VIEW[rawSection] ??
      // 「文件缺失」在旧侧边栏是 source=missing，在旧状态下拉是 status=missing
      (next.get('source') === 'missing' || next.get('status') === 'missing'
        ? 'missing'
        : next.get('status') === 'untagged'
          ? 'untagged'
          : undefined);
    if (implied) {
      next.set('view', implied);
      changed = true;
    }
  }

  // 只有「来自旧 section」的那次跳转才清理这些一次性参数。
  // 注意 source 在新工具栏里是合法参数（本地/网络筛选），不能无条件删除。
  if (rawSection && LEGACY_SECTIONS.has(rawSection)) {
    for (const key of ['source', 'status', 'asset']) {
      if (next.has(key)) {
        next.delete(key);
        changed = true;
      }
    }
  }

  // 4) runs 的默认 tab
  if (section === 'runs' && !next.get('tab')) {
    next.set('tab', rawSection === 'history' ? 'history' : 'tasks');
    changed = true;
  }

  if (!changed) return {};

  throw redirect(307, `${target.pathname}?${next.toString()}`);
};
