<script lang="ts">
  // 智能文件夹管理页面 — CRUD + 规则编辑器 + 媒体预览
  // 后端 API: GET/POST /smart-folders, PUT/DELETE /smart-folders/{id}, GET /smart-folders/{id}/preview
  // 规则格式参考 backend/app/rules/engine.py — { type: "group", logic: "and"|"or", children: [...] }
  import { onMount } from 'svelte';
  import { client, ApiError, BASE_URL } from '$lib/api/client';
  import {
    smartFoldersApi,
    type SmartFolder,
    type RuleGroup,
    type RuleCondition,
    type RuleNode,
    type PreviewMedia,
  } from '$lib/api/smart_folders';
  import { formatNumber, formatDuration, formatSize } from '$lib/utils/format';

  // ---- 类型 ----
  interface TagOption {
    id: number;
    name: string;
    tag_type_id: number;
    parent_id: number | null;
  }
  interface LibraryOption {
    id: number;
    name: string;
  }
  interface FlatNode {
    node: RuleNode;
    cond: RuleCondition;
    depth: number;
    path: number[];
    isGroup: boolean;
    parentPath: number[];
    valueType: string;
  }

  // ---- 维度与操作符配置（对齐 backend/app/rules/handlers.py）----
  const DIMENSIONS: Record<
    string,
    { label: string; operators: string[]; valueType: string; unit?: string }
  > = {
    tag: { label: '标签', operators: ['has', 'not_has', 'has_any', 'has_all'], valueType: 'tag' },
    rating: { label: '评分', operators: ['gte', 'lte', 'eq', 'is_null'], valueType: 'rating' },
    favorite: { label: '收藏', operators: ['eq'], valueType: 'bool' },
    media_type: { label: '来源类型', operators: ['eq'], valueType: 'media_type' },
    year: { label: '年份', operators: ['gte', 'lte', 'eq', 'between', 'is_null'], valueType: 'number', unit: '年' },
    duration: { label: '时长', operators: ['gt', 'lt', 'gte', 'lte', 'eq', 'between'], valueType: 'number', unit: '秒' },
    resolution: { label: '分辨率', operators: ['gte', 'lte', 'eq'], valueType: 'resolution' },
    file_size: { label: '文件大小', operators: ['gt', 'lt', 'gte', 'lte'], valueType: 'number', unit: 'MB' },
    library: { label: '资源库', operators: ['eq', 'in'], valueType: 'library' },
    season: { label: '季数', operators: ['eq', 'gte', 'lte', 'is_null'], valueType: 'number' },
    episode: { label: '集数', operators: ['eq', 'gte', 'lte', 'is_null'], valueType: 'number' },
    playback: { label: '播放进度', operators: ['gt', 'is_null'], valueType: 'number', unit: '秒' },
    watched: { label: '已看状态', operators: ['eq'], valueType: 'bool' },
    missing: { label: '本地缺失', operators: ['eq'], valueType: 'bool' },
    recent: { label: '添加时间(近N天)', operators: ['lte'], valueType: 'number', unit: '天' },
    no_tag: { label: '未分类', operators: ['eq'], valueType: 'bool' },
  };

  const OPERATOR_LABELS: Record<string, string> = {
    gt: '大于 >',
    lt: '小于 <',
    gte: '大于等于 ≥',
    lte: '小于等于 ≤',
    eq: '等于 =',
    between: '介于',
    has: '包含',
    not_has: '不包含',
    has_any: '包含任一',
    has_all: '包含全部',
    is_null: '为空',
    in: '属于',
  };

  const COLOR_PRESETS = [
    '#7b73ff', // indigo
    '#f5a623', // amber
    '#34d399', // green
    '#f87171', // red
    '#3b82f6', // blue
    '#a855f7', // purple
    '#ec4899', // pink
    '#06b6d4', // cyan
    '#f97316', // orange
    '#6b6b76', // gray
  ];

  const RESOLUTION_OPTIONS = [
    { value: 360, label: '360p' },
    { value: 480, label: '480p' },
    { value: 720, label: '720p' },
    { value: 1080, label: '1080p' },
    { value: 1440, label: '1440p' },
    { value: 2160, label: '4K (2160p)' },
    { value: 4320, label: '8K (4320p)' },
  ];

  const MEDIA_TYPE_OPTIONS = [
    { value: 'local', label: '本地' },
    { value: 'network', label: '网络' },
    { value: 'both', label: '本地 + 网络' },
  ];

  const MEDIA_TYPE_LABELS: Record<string, string> = {
    local: '本地',
    network: '网络',
    both: '本地+网络',
  };

  // ---- 状态 ----
  let folders = $state<SmartFolder[]>([]);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let tags = $state<TagOption[]>([]);
  let libraries = $state<LibraryOption[]>([]);

  // 创建/编辑对话框
  let dialogOpen = $state(false);
  let dialogMode = $state<'create' | 'edit'>('create');
  let dialogFolderId = $state<number | null>(null);
  let dialogName = $state('');
  let dialogColor = $state<string | null>(null);
  let dialogRule = $state<RuleGroup>({ type: 'group', logic: 'and', children: [] });
  let dialogSaving = $state(false);

  // 删除确认
  let deleteOpen = $state(false);
  let deleteTarget = $state<SmartFolder | null>(null);
  let deleting = $state(false);

  // 预览
  let previewOpen = $state(false);
  let previewFolder = $state<SmartFolder | null>(null);
  let previewMedia = $state<PreviewMedia[]>([]);
  let previewLoading = $state(false);

  // toast
  let toast = $state<{ msg: string; type: 'ok' | 'err' } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;

  // ---- 派生：扁平化规则树 ----
  const flatNodes = $derived.by(() => {
    if (!dialogOpen) return [];
    const out: FlatNode[] = [];
    const walk = (nodes: RuleNode[], depth: number, parentPath: number[]) => {
      nodes.forEach((node, idx) => {
        const path = [...parentPath, idx];
        const isGroup = node.type === 'group';
        const cond = isGroup ? ({} as RuleCondition) : (node as RuleCondition);
        const valueType = isGroup ? '' : getValueType(node as RuleCondition);
        out.push({ node, cond, depth, path, isGroup, parentPath, valueType });
        if (isGroup && node.children.length > 0) {
          walk(node.children, depth + 1, path);
        }
      });
    };
    walk(dialogRule.children, 0, []);
    return out;
  });

  // ---- Toast ----
  function showToast(msg: string, type: 'ok' | 'err' = 'ok'): void {
    toast = { msg, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2600);
  }

  // ---- 规则树工具 ----
  function cloneRule(r: RuleGroup): RuleGroup {
    return structuredClone(r);
  }

  function getGroup(root: RuleGroup, path: number[]): RuleGroup {
    let cur = root;
    for (const idx of path) {
      cur = cur.children[idx] as RuleGroup;
    }
    return cur;
  }

  function getNodeByPath(path: number[]): RuleNode {
    const idx = path[path.length - 1];
    const parentPath = path.slice(0, -1);
    return getGroup(dialogRule, parentPath).children[idx];
  }

  function addChild(parentPath: number[], child: RuleNode): void {
    const next = cloneRule(dialogRule);
    const parent = getGroup(next, parentPath);
    parent.children.push(child);
    dialogRule = next;
  }

  function removeNode(path: number[]): void {
    const next = cloneRule(dialogRule);
    const idx = path[path.length - 1];
    const parentPath = path.slice(0, -1);
    const parent = getGroup(next, parentPath);
    parent.children.splice(idx, 1);
    dialogRule = next;
  }

  function updateNode(path: number[], patch: Record<string, unknown>): void {
    const next = cloneRule(dialogRule);
    const idx = path[path.length - 1];
    const parentPath = path.slice(0, -1);
    const parent = getGroup(next, parentPath);
    parent.children[idx] = { ...parent.children[idx], ...patch } as RuleNode;
    dialogRule = next;
  }

  function moveNode(path: number[], dir: -1 | 1): void {
    const next = cloneRule(dialogRule);
    const idx = path[path.length - 1];
    const parentPath = path.slice(0, -1);
    const parent = getGroup(next, parentPath);
    const target = idx + dir;
    if (target < 0 || target >= parent.children.length) return;
    [parent.children[idx], parent.children[target]] = [
      parent.children[target],
      parent.children[idx],
    ];
    dialogRule = next;
  }

  function addCondition(parentPath: number[]): void {
    addChild(parentPath, {
      type: 'condition',
      dimension: 'tag',
      operator: 'has',
      value: tags[0]?.id ?? 0,
    });
  }

  function addGroup(parentPath: number[]): void {
    addChild(parentPath, {
      type: 'group',
      logic: 'and',
      children: [],
    });
  }

  // ---- 维度/操作符切换 ----
  function onDimensionChange(path: number[], dimension: string): void {
    const cfg = DIMENSIONS[dimension];
    const op = cfg.operators[0];
    const value = defaultValueFor(dimension, op);
    updateNode(path, { dimension, operator: op, value });
  }

  function onOperatorChange(path: number[], operator: string): void {
    const cond = getNodeByPath(path) as RuleCondition;
    const value = defaultValueFor(cond.dimension, operator, cond.value);
    updateNode(path, { operator, value });
  }

  function defaultValueFor(dimension: string, operator: string, prev?: unknown): unknown {
    if (operator === 'is_null') return true;
    if (operator === 'between') return Array.isArray(prev) ? prev : [0, 0];
    if (operator === 'has_any' || operator === 'has_all' || operator === 'in') {
      return Array.isArray(prev) ? prev : [];
    }
    if (dimension === 'favorite') return true;
    if (dimension === 'watched' || dimension === 'missing' || dimension === 'no_tag') return true;
    if (dimension === 'tag') return tags[0]?.id ?? 0;
    if (dimension === 'library') return libraries[0]?.id ?? 0;
    if (dimension === 'resolution') return 1080;
    if (dimension === 'media_type') return 'local';
    if (dimension === 'rating') return 3;
    if (dimension === 'year') return 2024;
    return 0;
  }

  function getValueType(node: RuleCondition): string {
    const cfg = DIMENSIONS[node.dimension];
    if (!cfg) return 'number';
    if (node.operator === 'is_null') return 'none';
    if (node.operator === 'between') return 'range';
    if (node.operator === 'has_any' || node.operator === 'has_all' || node.operator === 'in')
      return 'list';
    return cfg.valueType;
  }

  // ---- 值渲染辅助 ----
  function valueAsNum(v: unknown): number {
    return typeof v === 'number' ? v : 0;
  }
  function valueAsBool(v: unknown): boolean {
    return v === true || v === 'true';
  }
  function valueAsList(v: unknown): number[] {
    return Array.isArray(v) ? (v as number[]) : [];
  }
  function listToText(v: unknown): string {
    return valueAsList(v).join(', ');
  }

  // ---- 名称解析 ----
  function tagName(id: number): string {
    return tags.find((t) => t.id === id)?.name ?? `标签#${id}`;
  }
  function libName(id: number): string {
    return libraries.find((l) => l.id === id)?.name ?? `库#${id}`;
  }
  function mediaThumbUrl(id: number): string {
    return `${BASE_URL}/media/${id}/thumbnail`;
  }

  // 安全校验颜色值
  function safeColor(c: string | null | undefined): string {
    return /^#[0-9a-fA-F]{6}$/.test(c ?? '') ? (c as string) : '';
  }

  // ---- 规则描述（人类可读）----
  function describeRule(rule: RuleGroup | null | undefined): string {
    if (!rule || !rule.children || rule.children.length === 0) {
      return '匹配所有媒体';
    }
    const parts = rule.children.map((child) => {
      if (child.type === 'group') {
        return `(${describeRule(child as RuleGroup)})`;
      }
      return describeCondition(child as RuleCondition);
    });
    const logic = rule.logic === 'and' ? ' 且 ' : ' 或 ';
    return parts.join(logic);
  }

  function describeCondition(cond: RuleCondition): string {
    const dim = DIMENSIONS[cond.dimension];
    const dimLabel = dim?.label ?? cond.dimension;

    if (cond.operator === 'is_null') {
      return `${dimLabel} ${cond.value ? '为空' : '不为空'}`;
    }

    const opLabel = OPERATOR_LABELS[cond.operator] ?? cond.operator;
    let valueStr = '';

    if (cond.dimension === 'tag') {
      if (Array.isArray(cond.value)) {
        valueStr = cond.value.map((v) => tagName(Number(v))).join(', ');
      } else {
        valueStr = tagName(Number(cond.value));
      }
    } else if (cond.dimension === 'library') {
      if (Array.isArray(cond.value)) {
        valueStr = cond.value.map((v) => libName(Number(v))).join(', ');
      } else {
        valueStr = libName(Number(cond.value));
      }
    } else if (cond.dimension === 'favorite') {
      valueStr = cond.value ? '是' : '否';
    } else if (cond.dimension === 'watched' || cond.dimension === 'missing' || cond.dimension === 'no_tag') {
      valueStr = cond.value ? '是' : '否';
    } else if (cond.dimension === 'media_type') {
      valueStr = MEDIA_TYPE_LABELS[String(cond.value)] ?? String(cond.value);
    } else if (cond.dimension === 'rating') {
      const r = typeof cond.value === 'number' ? cond.value : 0;
      valueStr = `${'★'.repeat(r)} (${r})`;
    } else if (cond.dimension === 'resolution') {
      const opt = RESOLUTION_OPTIONS.find((o) => o.value === Number(cond.value));
      valueStr = opt?.label ?? String(cond.value);
    } else if (cond.operator === 'between' && Array.isArray(cond.value)) {
      valueStr = `${cond.value[0]} ~ ${cond.value[1]}`;
      if (dim?.unit) valueStr += ` ${dim.unit}`;
    } else {
      valueStr = String(cond.value);
      if (dim?.unit) valueStr += ` ${dim.unit}`;
    }

    return `${dimLabel} ${opLabel} ${valueStr}`;
  }

  // ---- 数据加载 ----
  async function loadAll(): Promise<void> {
    loading = true;
    error = null;
    try {
      const [list, tagList, libList] = await Promise.all([
        smartFoldersApi.list(),
        client.get<TagOption[]>('/tags').catch(() => []),
        client.get<LibraryOption[]>('/libraries').catch(() => []),
      ]);
      folders = list ?? [];
      tags = tagList ?? [];
      libraries = libList ?? [];
    } catch (e) {
      error = e instanceof ApiError ? '加载智能文件夹失败' : '加载失败，请检查后端服务';
    } finally {
      loading = false;
    }
  }

  // ---- 对话框：创建/编辑 ----
  function openCreate(): void {
    dialogMode = 'create';
    dialogFolderId = null;
    dialogName = '';
    dialogColor = null;
    dialogRule = { type: 'group', logic: 'and', children: [] };
    dialogSaving = false;
    dialogOpen = true;
  }

  function openEdit(folder: SmartFolder): void {
    dialogMode = 'edit';
    dialogFolderId = folder.id;
    dialogName = folder.name;
    dialogColor = folder.color;
    dialogRule = cloneRule(folder.rule_json);
    dialogSaving = false;
    dialogOpen = true;
  }

  function closeDialog(): void {
    if (dialogSaving) return;
    dialogOpen = false;
  }

  async function saveFolder(): Promise<void> {
    const name = dialogName.trim();
    if (!name) return;
    dialogSaving = true;
    try {
      const payload = {
        name,
        color: dialogColor,
        rule_json: dialogRule,
      };
      if (dialogMode === 'create') {
        const created = await smartFoldersApi.create(payload);
        folders = [...folders, created];
        showToast('已创建智能文件夹');
      } else if (dialogFolderId !== null) {
        const updated = await smartFoldersApi.update(dialogFolderId, payload);
        folders = folders.map((f) => (f.id === dialogFolderId ? { ...f, ...updated } : f));
        showToast('已保存修改');
      }
      dialogOpen = false;
    } catch {
      showToast('保存失败', 'err');
    } finally {
      dialogSaving = false;
    }
  }

  // ---- 删除 ----
  function askDelete(folder: SmartFolder): void {
    deleteTarget = folder;
    deleting = false;
    deleteOpen = true;
  }

  async function confirmDelete(): Promise<void> {
    if (!deleteTarget || deleting) return;
    const target = deleteTarget;
    deleting = true;
    try {
      await smartFoldersApi.delete(target.id);
      folders = folders.filter((f) => f.id !== target.id);
      showToast('已删除');
    } catch {
      showToast('删除失败', 'err');
    } finally {
      deleting = false;
      deleteOpen = false;
      deleteTarget = null;
    }
  }

  // ---- 预览 ----
  async function openPreview(folder: SmartFolder): Promise<void> {
    previewFolder = folder;
    previewOpen = true;
    previewLoading = true;
    previewMedia = [];
    try {
      const media = await smartFoldersApi.preview(folder.id);
      previewMedia = media ?? [];
      // 同步本地 preview_count
      folders = folders.map((f) =>
        f.id === folder.id ? { ...f, preview_count: previewMedia.length } : f
      );
    } catch {
      showToast('预览失败', 'err');
    } finally {
      previewLoading = false;
    }
  }

  // ---- 生命周期 ----
  onMount(() => {
    loadAll();
    return () => {
      if (toastTimer) clearTimeout(toastTimer);
    };
  });
</script>

<svelte:head><title>智能文件夹 — vitoice</title></svelte:head>

<div class="sf-page">
  <!-- 页头 -->
  <div class="page-head">
    <div class="head-left">
      <h1>智能文件夹</h1>
      <p>通过规则自动组织媒体，创建动态虚拟文件夹。</p>
    </div>
    <div class="head-right">
      <div class="stat-pill">
        <span class="stat-num">{formatNumber(folders.length)}</span>
        <span class="stat-label">个文件夹</span>
      </div>
      <button class="btn primary" onclick={openCreate}>+ 新建文件夹</button>
    </div>
  </div>

  <!-- 列表 -->
  {#if loading}
    <div class="state">加载中…</div>
  {:else if error}
    <div class="state error">{error}</div>
  {:else if folders.length === 0}
    <div class="empty-state">
      <div class="empty-icon">📁</div>
      <h2>还没有智能文件夹</h2>
      <p>创建一个智能文件夹，通过标签、评分、类型等条件自动筛选媒体。</p>
      <button class="btn primary" onclick={openCreate}>新建智能文件夹</button>
    </div>
  {:else}
    <div class="sf-grid">
      {#each folders as f (f.id)}
        <div
          class="sf-card"
          style={`--card-color:${safeColor(f.color) || 'var(--accent)'}`}
        >
          <div class="card-color-bar"></div>
          <div class="card-body">
            <div class="card-head">
              <span class="card-dot"></span>
              <h3 class="card-name" title={f.name}>{f.name}</h3>
            </div>
            <p class="card-desc" title={describeRule(f.rule_json)}>{describeRule(f.rule_json)}</p>
            <div class="card-foot">
              <span class="card-count">
                <span class="count-num">{formatNumber(f.preview_count)}</span>
                <span class="count-label">个媒体</span>
              </span>
              <div class="card-actions">
                <button class="action-btn preview" title="预览匹配媒体" onclick={() => openPreview(f)}>预览</button>
                {#if !f.is_system}
                  <button class="action-btn edit" title="编辑" onclick={() => openEdit(f)}>编辑</button>
                  <button class="action-btn danger" title="删除" onclick={() => askDelete(f)}>删除</button>
                {:else}
                  <span class="system-badge" title="系统预置文件夹">系统</span>
                {/if}
              </div>
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- 创建/编辑对话框 -->
{#if dialogOpen}
  <div
    class="modal-overlay"
    onclick={() => closeDialog()}
    onkeydown={(e) => { if (e.key === 'Escape') { e.preventDefault(); closeDialog(); } }}
    role="presentation"
  >
    <div
      class="modal dialog-modal"
      onclick={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <h3>{dialogMode === 'create' ? '新建智能文件夹' : '编辑智能文件夹'}</h3>

      <div class="dialog-body">
        <!-- 名称 -->
        <div class="form-group">
          <label for="sf-name">名称</label>
          <input
            id="sf-name"
            type="text"
            class="text-input"
            value={dialogName}
            oninput={(e) => { dialogName = (e.target as HTMLInputElement).value; }}
            placeholder="文件夹名称"
          />
        </div>

        <!-- 颜色 -->
        <div class="form-group">
          <span class="field-label">颜色标识</span>
          <div class="color-picker">
            <button
              type="button"
              class="color-swatch none"
              class:active={dialogColor === null}
              onclick={() => { dialogColor = null; }}
              title="无颜色"
            >
              <span class="none-icon">✕</span>
            </button>
            {#each COLOR_PRESETS as c (c)}
              <button
                type="button"
                class="color-swatch"
                class:active={dialogColor === c}
                style={`background:${c}`}
                onclick={() => { dialogColor = c; }}
                title={c}
              ></button>
            {/each}
          </div>
        </div>

        <!-- 规则编辑器 -->
        <div class="form-group">
          <span class="field-label">匹配规则</span>
          <div class="rule-tree">
            <!-- 根组逻辑 -->
            <div class="group-head root">
              <span class="group-label">匹配</span>
              <div class="logic-toggle">
                <button
                  class:active={dialogRule.logic === 'and'}
                  onclick={() => { dialogRule = { ...dialogRule, logic: 'and' }; }}
                >全部满足 (AND)</button>
                <button
                  class:active={dialogRule.logic === 'or'}
                  onclick={() => { dialogRule = { ...dialogRule, logic: 'or' }; }}
                >任一满足 (OR)</button>
              </div>
              <span class="group-bracket">以下条件</span>
            </div>

            <!-- 规则节点 -->
            {#if flatNodes.length === 0}
              <div class="empty-rules">
                <div class="empty-rules-text">暂无条件，添加第一个条件或条件组</div>
              </div>
            {:else}
              {#each flatNodes as fn (fn.path.join('-'))}
                <div class="rule-node" style={`margin-left:${fn.depth * 24}px`}>
                  {#if fn.isGroup}
                    <!-- 组节点 -->
                    <div class="node group-node">
                      <div class="node-line"></div>
                      <div class="group-box">
                        <div class="group-head">
                          <span class="group-label-sm">组</span>
                          <div class="logic-toggle sm">
                            <button
                              class:active={(fn.node as RuleGroup).logic === 'and'}
                              onclick={() => updateNode(fn.path, { logic: 'and' })}
                            >AND</button>
                            <button
                              class:active={(fn.node as RuleGroup).logic === 'or'}
                              onclick={() => updateNode(fn.path, { logic: 'or' })}
                            >OR</button>
                          </div>
                          <div class="node-actions">
                            <button class="icon-btn" title="上移" onclick={() => moveNode(fn.path, -1)}>↑</button>
                            <button class="icon-btn" title="下移" onclick={() => moveNode(fn.path, 1)}>↓</button>
                            <button class="icon-btn danger" title="删除组" onclick={() => removeNode(fn.path)}>✕</button>
                          </div>
                        </div>
                        {#if (fn.node as RuleGroup).children.length === 0}
                          <div class="group-empty">空组</div>
                        {/if}
                        <div class="group-add">
                          <button class="add-cond-btn" onclick={() => addCondition(fn.path)}>+ 条件</button>
                          <button class="add-group-btn" onclick={() => addGroup(fn.path)}>+ 子组</button>
                        </div>
                      </div>
                    </div>
                  {:else}
                    {@const _vt = fn.valueType}
                    <!-- 条件节点 -->
                    <div class="node cond-node">
                      <div class="node-line"></div>
                      <div class="cond-box">
                        <select
                          class="sel dim"
                          value={fn.cond.dimension}
                          onchange={(e) => onDimensionChange(fn.path, (e.target as HTMLSelectElement).value)}
                        >
                          {#each Object.entries(DIMENSIONS) as [key, cfg] (key)}
                            <option value={key}>{cfg.label}</option>
                          {/each}
                        </select>

                        <select
                          class="sel op"
                          value={fn.cond.operator}
                          onchange={(e) => onOperatorChange(fn.path, (e.target as HTMLSelectElement).value)}
                        >
                          {#each DIMENSIONS[fn.cond.dimension].operators as op (op)}
                            <option value={op}>{OPERATOR_LABELS[op] ?? op}</option>
                          {/each}
                        </select>

                        {#if _vt === 'none'}
                          <span class="no-value">（无需值）</span>
                        {:else if _vt === 'bool'}
                          <button
                            type="button"
                            class="toggle"
                            class:on={valueAsBool(fn.cond.value)}
                            onclick={() => updateNode(fn.path, { value: !valueAsBool(fn.cond.value) })}
                            role="switch"
                            aria-checked={valueAsBool(fn.cond.value)}
                            aria-label="切换条件值"
                          >
                            <span class="knob"></span>
                          </button>
                        {:else if _vt === 'tag'}
                          <select
                            class="sel val"
                            value={valueAsNum(fn.cond.value)}
                            onchange={(e) => updateNode(fn.path, { value: Number((e.target as HTMLSelectElement).value) })}
                          >
                            {#each tags as t (t.id)}
                              <option value={t.id}>{t.name}</option>
                            {/each}
                          </select>
                        {:else if _vt === 'library'}
                          <select
                            class="sel val"
                            value={valueAsNum(fn.cond.value)}
                            onchange={(e) => updateNode(fn.path, { value: Number((e.target as HTMLSelectElement).value) })}
                          >
                            {#each libraries as l (l.id)}
                              <option value={l.id}>{l.name}</option>
                            {/each}
                          </select>
                        {:else if _vt === 'resolution'}
                          <select
                            class="sel val"
                            value={valueAsNum(fn.cond.value)}
                            onchange={(e) => updateNode(fn.path, { value: Number((e.target as HTMLSelectElement).value) })}
                          >
                            {#each RESOLUTION_OPTIONS as r (r.value)}
                              <option value={r.value}>{r.label}</option>
                            {/each}
                          </select>
                        {:else if _vt === 'media_type'}
                          <select
                            class="sel val"
                            value={String(fn.cond.value)}
                            onchange={(e) => updateNode(fn.path, { value: (e.target as HTMLSelectElement).value })}
                          >
                            {#each MEDIA_TYPE_OPTIONS as m (m.value)}
                              <option value={m.value}>{m.label}</option>
                            {/each}
                          </select>
                        {:else if _vt === 'rating'}
                          <select
                            class="sel val"
                            value={valueAsNum(fn.cond.value)}
                            onchange={(e) => updateNode(fn.path, { value: Number((e.target as HTMLSelectElement).value) })}
                          >
                            {#each [1, 2, 3, 4, 5] as r (r)}
                              <option value={r}>{'★'.repeat(r)} ({r})</option>
                            {/each}
                          </select>
                        {:else if _vt === 'range'}
                          <div class="range-inputs">
                            <input
                              type="number"
                              class="num-input"
                              value={valueAsList(fn.cond.value)[0] ?? 0}
                              onchange={(e) => updateNode(fn.path, { value: [Number((e.target as HTMLInputElement).value), valueAsList(fn.cond.value)[1] ?? 0] })}
                            />
                            <span class="range-sep">~</span>
                            <input
                              type="number"
                              class="num-input"
                              value={valueAsList(fn.cond.value)[1] ?? 0}
                              onchange={(e) => updateNode(fn.path, { value: [valueAsList(fn.cond.value)[0] ?? 0, Number((e.target as HTMLInputElement).value)] })}
                            />
                            <span class="unit">{DIMENSIONS[fn.cond.dimension].unit ?? ''}</span>
                          </div>
                        {:else if _vt === 'list'}
                          <input
                            type="text"
                            class="text-input val"
                            value={listToText(fn.cond.value)}
                            placeholder="ID, ID, …"
                            onchange={(e) => updateNode(fn.path, { value: (e.target as HTMLInputElement).value.split(',').map((s) => Number(s.trim())).filter((n) => !isNaN(n)) })}
                          />
                          <span class="list-hint">{fn.cond.dimension === 'tag' ? '标签ID' : '库ID'}</span>
                        {:else}
                          <input
                            type="number"
                            class="num-input val"
                            value={valueAsNum(fn.cond.value)}
                            onchange={(e) => updateNode(fn.path, { value: Number((e.target as HTMLInputElement).value) })}
                          />
                          {#if DIMENSIONS[fn.cond.dimension].unit}
                            <span class="unit">{DIMENSIONS[fn.cond.dimension].unit}</span>
                          {/if}
                        {/if}

                        <div class="node-actions">
                          <button class="icon-btn" title="上移" onclick={() => moveNode(fn.path, -1)}>↑</button>
                          <button class="icon-btn" title="下移" onclick={() => moveNode(fn.path, 1)}>↓</button>
                          <button class="icon-btn danger" title="删除" onclick={() => removeNode(fn.path)}>✕</button>
                        </div>
                      </div>
                    </div>
                  {/if}
                </div>
              {/each}
            {/if}

            <!-- 根级添加 -->
            <div class="root-add">
              <button class="add-cond-btn" onclick={() => addCondition([])}>+ 添加条件</button>
              <button class="add-group-btn" onclick={() => addGroup([])}>+ 添加条件组</button>
            </div>
          </div>
        </div>

        <!-- JSON 预览 -->
        <details class="json-preview">
          <summary>查看规则 JSON</summary>
          <pre>{JSON.stringify(dialogRule, null, 2)}</pre>
        </details>
      </div>

      <div class="modal-actions">
        <button class="btn ghost" onclick={() => closeDialog()} disabled={dialogSaving}>取消</button>
        <button class="btn primary" onclick={saveFolder} disabled={dialogSaving || !dialogName.trim()}>
          {dialogSaving ? '保存中…' : '保存'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- 删除确认 -->
{#if deleteOpen}
  <div
    class="modal-overlay"
    onclick={() => { if (!deleting) { deleteOpen = false; deleteTarget = null; } }}
    onkeydown={(e) => { if (e.key === 'Escape') { e.preventDefault(); if (!deleting) { deleteOpen = false; deleteTarget = null; } } }}
    role="presentation"
  >
    <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" tabindex="-1">
      <h3>删除智能文件夹</h3>
      <p>确定删除「{deleteTarget?.name}」？该操作仅删除文件夹定义，不会删除任何媒体文件。</p>
      <div class="modal-actions">
        <button class="btn ghost" onclick={() => { deleteOpen = false; deleteTarget = null; }} disabled={deleting}>取消</button>
        <button class="btn danger" onclick={confirmDelete} disabled={deleting}>
          {deleting ? '删除中…' : '删除'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- 预览弹窗 -->
{#if previewOpen}
  <div
    class="modal-overlay"
    onclick={() => { previewOpen = false; }}
    onkeydown={(e) => { if (e.key === 'Escape') { e.preventDefault(); previewOpen = false; } }}
    role="presentation"
  >
    <div class="modal preview-modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" tabindex="-1">
      <div class="preview-head">
        <div class="preview-title-area">
          <div class="preview-title-row">
            <span class="preview-dot" style={`background:${safeColor(previewFolder?.color) || 'var(--accent)'}`}></span>
            <h3>{previewFolder?.name}</h3>
          </div>
          <p class="preview-desc">{previewFolder ? describeRule(previewFolder.rule_json) : ''}</p>
        </div>
        <button class="btn ghost" onclick={() => { previewOpen = false; }}>关闭</button>
      </div>
      <div class="preview-body">
        {#if previewLoading}
          <div class="state">加载中…</div>
        {:else if previewMedia.length === 0}
          <div class="state empty-preview">
            <div class="empty-icon">📭</div>
            <div>没有匹配的媒体</div>
          </div>
        {:else}
          <div class="preview-meta-bar">
            共 {formatNumber(previewMedia.length)} 个匹配媒体
          </div>
          <div class="media-list">
            {#each previewMedia as m (m.id)}
              <div class="media-item">
                <div class="media-thumb">
                  <img
                    src={mediaThumbUrl(m.id)}
                    alt={m.title}
                    loading="lazy"
                    onerror={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                  />
                  <div class="thumb-fallback">🎬</div>
                </div>
                <div class="media-info">
                  <div class="media-title" title={m.title}>{m.title}</div>
                  <div class="media-meta">
                    {#if m.year}<span class="meta-chip">{m.year}</span>{/if}
                    {#if m.duration}<span class="meta-chip">{formatDuration(m.duration)}</span>{/if}
                    {#if m.file_size}<span class="meta-chip">{formatSize(m.file_size)}</span>{/if}
                    {#if m.width && m.height}<span class="meta-chip">{m.width}×{m.height}</span>{/if}
                    {#if m.rating}<span class="meta-chip star">{'★'.repeat(m.rating)}</span>{/if}
                    {#if m.is_favorite}<span class="meta-chip fav">♥ 收藏</span>{/if}
                  </div>
                  {#if m.tags && m.tags.length > 0}
                    <div class="media-tags">
                      {#each m.tags.slice(0, 6) as t (t.id)}
                        <span class="media-tag">{t.name}</span>
                      {/each}
                      {#if m.tags.length > 6}
                        <span class="media-tag more">+{m.tags.length - 6}</span>
                      {/if}
                    </div>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

{#if toast}
  <div class="toast" class:ok={toast.type === 'ok'} class:err={toast.type === 'err'}>{toast.msg}</div>
{/if}

<style>
  .sf-page {
    flex: 1;
    overflow-y: auto;
    padding: 24px 28px 40px;
  }

  /* ---- 页头 ---- */
  .page-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 24px;
  }

  .head-left h1 {
    margin: 0 0 4px;
    font-size: 22px;
    font-weight: 700;
    color: var(--ink);
  }

  .head-left p {
    margin: 0;
    font-size: 13px;
    color: var(--ink-tertiary);
  }

  .head-right {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .stat-pill {
    display: flex;
    align-items: baseline;
    gap: 4px;
    padding: 6px 14px;
    background: var(--bg-surface);
    border-radius: var(--radius-full);
  }

  .stat-num {
    font-size: 16px;
    font-weight: 700;
    color: var(--accent);
    font-variant-numeric: tabular-nums;
  }

  .stat-label {
    font-size: 12px;
    color: var(--ink-tertiary);
  }

  /* ---- 按钮 ---- */
  .btn {
    height: 36px;
    padding: 0 16px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 13px;
    font-weight: 500;
    transition: all 200ms ease;
  }

  .btn:hover:not(:disabled) {
    border-color: var(--ink-tertiary);
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn.ghost {
    background: var(--bg-surface);
  }

  .btn.primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .btn.primary:hover:not(:disabled) {
    filter: brightness(1.08);
  }

  .btn.danger {
    background: #ff3b30;
    border-color: #ff3b30;
    color: #fff;
  }

  .btn.danger:hover:not(:disabled) {
    filter: brightness(1.08);
  }

  /* ---- 空状态 ---- */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 80px 20px;
    text-align: center;
  }

  .empty-icon {
    font-size: 48px;
    opacity: 0.5;
    margin-bottom: 16px;
  }

  .empty-state h2 {
    margin: 0 0 8px;
    font-size: 18px;
    color: var(--ink);
  }

  .empty-state p {
    margin: 0 0 20px;
    font-size: 13px;
    color: var(--ink-tertiary);
  }

  .state {
    padding: 80px 0;
    text-align: center;
    color: var(--ink-tertiary);
    font-size: 14px;
  }

  .state.error {
    color: #ff3b30;
  }

  /* ---- 卡片网格 ---- */
  .sf-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 16px;
  }

  .sf-card {
    position: relative;
    border: 1px solid var(--rule);
    border-radius: var(--radius-lg);
    background: var(--bg-elevated);
    overflow: hidden;
    transition: border-color 200ms, box-shadow 200ms;
  }

  .sf-card:hover {
    border-color: var(--card-color);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  }

  .card-color-bar {
    height: 3px;
    background: var(--card-color);
  }

  .card-body {
    padding: 16px 18px;
  }

  .card-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }

  .card-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    background: var(--card-color);
    flex-shrink: 0;
  }

  .card-name {
    margin: 0;
    font-size: 15px;
    font-weight: 700;
    color: var(--ink);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .card-desc {
    margin: 0 0 14px;
    font-size: 12.5px;
    color: var(--ink-tertiary);
    line-height: 1.5;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    min-height: 38px;
  }

  .card-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .card-count {
    display: flex;
    align-items: baseline;
    gap: 4px;
  }

  .count-num {
    font-size: 18px;
    font-weight: 700;
    color: var(--accent);
    font-variant-numeric: tabular-nums;
  }

  .count-label {
    font-size: 11.5px;
    color: var(--ink-tertiary);
  }

  .card-actions {
    display: flex;
    gap: 4px;
  }

  .action-btn {
    height: 28px;
    padding: 0 10px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 12px;
    font-weight: 500;
    transition: all 200ms ease;
  }

  .action-btn:hover {
    border-color: var(--ink-tertiary);
  }

  .action-btn.preview:hover {
    border-color: var(--accent2);
    color: var(--accent2);
  }

  .action-btn.edit:hover {
    border-color: var(--accent);
    color: var(--accent);
  }

  .action-btn.danger:hover {
    border-color: #ff3b30;
    color: #ff3b30;
  }

  .system-badge {
    height: 28px;
    padding: 0 10px;
    border-radius: var(--radius);
    background: var(--bg-elevated);
    border: 1px solid var(--rule);
    color: var(--ink-tertiary);
    font-size: 12px;
    font-weight: 500;
    line-height: 26px;
    user-select: none;
  }

  /* ---- Modal 通用 ---- */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: fade-in 200ms ease;
    padding: 20px;
  }

  .modal {
    width: 420px;
    max-width: 90vw;
    background: var(--bg-elevated);
    border: 1px solid var(--rule);
    border-radius: var(--radius-lg);
    padding: 24px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
    animation: scale-in 200ms var(--ease-spring);
  }

  .modal h3 {
    margin: 0 0 16px;
    font-size: 17px;
    color: var(--ink);
  }

  .modal p {
    margin: 0 0 20px;
    font-size: 13px;
    color: var(--ink-tertiary);
    line-height: 1.6;
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }

  /* ---- 创建/编辑对话框 ---- */
  .dialog-modal {
    width: 720px;
    max-width: 94vw;
    max-height: 88vh;
    display: flex;
    flex-direction: column;
  }

  .dialog-body {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin-bottom: 20px;
    padding-right: 4px;
  }

  .form-group label,
  .form-group .field-label {
    display: block;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--ink);
    margin-bottom: 6px;
  }

  .text-input {
    width: 100%;
    height: 36px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 13px;
    font-family: inherit;
    transition: border-color 200ms;
  }

  .text-input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .text-input.val {
    width: 120px;
  }

  /* ---- 颜色选择器 ---- */
  .color-picker {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .color-swatch {
    width: 28px;
    height: 28px;
    border-radius: var(--radius);
    border: 2px solid transparent;
    cursor: pointer;
    transition: all 200ms;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
  }

  .color-swatch:hover {
    transform: scale(1.1);
  }

  .color-swatch.active {
    border-color: var(--ink);
    box-shadow: 0 0 0 2px var(--bg-elevated), 0 0 0 4px var(--accent);
  }

  .color-swatch.none {
    background: var(--bg-surface);
    border: 1px dashed var(--rule);
  }

  .none-icon {
    font-size: 12px;
    color: var(--ink-tertiary);
  }

  /* ---- 规则树 ---- */
  .rule-tree {
    border: 1px solid var(--rule);
    border-radius: var(--radius-md);
    padding: 16px;
    background: var(--bg-surface);
  }

  .group-head.root {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
    padding-bottom: 12px;
    border-bottom: 1px dashed var(--rule);
  }

  .group-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
  }

  .group-bracket {
    font-size: 12.5px;
    color: var(--ink-tertiary);
  }

  .logic-toggle {
    display: inline-flex;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    overflow: hidden;
  }

  .logic-toggle button {
    padding: 4px 12px;
    border: none;
    background: var(--bg-elevated);
    color: var(--ink-tertiary);
    font-size: 12px;
    transition: all 200ms;
  }

  .logic-toggle button.active {
    background: var(--accent);
    color: #fff;
  }

  .logic-toggle.sm button {
    padding: 2px 8px;
    font-size: 11px;
  }

  .rule-node {
    position: relative;
    margin-bottom: 8px;
  }

  .node-line {
    position: absolute;
    left: -12px;
    top: 0;
    bottom: 0;
    width: 2px;
    background: var(--rule);
    border-radius: 1px;
  }

  .cond-box {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    background: var(--bg-elevated);
    border-radius: var(--radius);
    flex-wrap: wrap;
  }

  .group-box {
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    padding: 10px 12px;
    background: var(--bg-surface);
  }

  .group-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }

  .group-label-sm {
    font-size: 11.5px;
    font-weight: 600;
    color: var(--ink-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .group-empty {
    font-size: 12px;
    color: var(--ink-tertiary);
    padding: 4px 0;
    font-style: italic;
  }

  .group-add {
    display: flex;
    gap: 6px;
    margin-top: 8px;
  }

  .sel {
    height: 30px;
    padding: 0 24px 0 8px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 12.5px;
    font-family: inherit;
    transition: border-color 200ms;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%236e6e73'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 8px center;
  }

  .sel:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .sel.dim {
    font-weight: 600;
    min-width: 90px;
  }

  .sel.op {
    min-width: 110px;
  }

  .sel.val {
    min-width: 100px;
  }

  .num-input {
    height: 30px;
    padding: 0 8px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 12.5px;
    font-family: inherit;
    transition: border-color 200ms;
    width: 80px;
  }

  .num-input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .num-input.val {
    width: 90px;
  }

  .unit {
    font-size: 11.5px;
    color: var(--ink-tertiary);
  }

  .range-inputs {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .range-sep {
    color: var(--ink-tertiary);
    font-size: 12px;
  }

  .list-hint {
    font-size: 11px;
    color: var(--ink-tertiary);
  }

  .no-value {
    font-size: 12.5px;
    color: var(--ink-tertiary);
    font-style: italic;
  }

  .toggle {
    width: 38px;
    height: 22px;
    border-radius: var(--radius-full);
    background: var(--rule);
    border: none;
    padding: 2px;
    display: flex;
    align-items: center;
    transition: background 200ms ease;
    flex-shrink: 0;
    cursor: pointer;
  }

  .toggle.on {
    background: var(--accent);
  }

  .knob {
    width: 18px;
    height: 18px;
    border-radius: var(--radius-full);
    background: #fff;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
    transition: transform 200ms ease;
  }

  .toggle.on .knob {
    transform: translateX(16px);
  }

  .node-actions {
    display: flex;
    gap: 2px;
    margin-left: auto;
  }

  .icon-btn {
    width: 24px;
    height: 24px;
    border: none;
    background: none;
    color: var(--ink-tertiary);
    font-size: 12px;
    border-radius: var(--radius);
    transition: all 200ms;
    cursor: pointer;
  }

  .icon-btn:hover {
    background: var(--bg-hover);
    color: var(--ink);
  }

  .icon-btn.danger:hover {
    color: #ff3b30;
  }

  .empty-rules {
    padding: 24px;
    text-align: center;
  }

  .empty-rules-text {
    font-size: 13px;
    color: var(--ink-tertiary);
  }

  .root-add {
    display: flex;
    gap: 8px;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px dashed var(--rule);
  }

  .add-cond-btn,
  .add-group-btn {
    height: 28px;
    padding: 0 12px;
    border: 1px dashed var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink-tertiary);
    font-size: 12px;
    transition: all 200ms ease;
  }

  .add-cond-btn:hover {
    border-color: var(--accent);
    border-style: solid;
    color: var(--accent);
    background: var(--accent-soft);
  }

  .add-group-btn:hover {
    border-color: var(--accent2);
    border-style: solid;
    color: var(--accent2);
    background: var(--accent2-soft);
  }

  /* ---- JSON 预览 ---- */
  .json-preview {
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-surface);
  }

  .json-preview summary {
    padding: 8px 12px;
    cursor: pointer;
    font-size: 12px;
    color: var(--ink-tertiary);
    font-weight: 500;
    user-select: none;
  }

  .json-preview pre {
    margin: 0;
    padding: 0 12px 12px;
    font-size: 11.5px;
    color: var(--ink);
    font-family: var(--font-mono);
    overflow-x: auto;
    line-height: 1.5;
  }

  /* ---- 预览弹窗 ---- */
  .preview-modal {
    width: 800px;
    max-width: 94vw;
    max-height: 85vh;
    display: flex;
    flex-direction: column;
    padding: 0;
  }

  .preview-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding: 20px 24px 16px;
    border-bottom: 1px solid var(--rule);
    gap: 12px;
  }

  .preview-title-area {
    flex: 1;
    min-width: 0;
  }

  .preview-title-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .preview-dot {
    width: 10px;
    height: 10px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
  }

  .preview-head h3 {
    margin: 0;
    font-size: 17px;
    color: var(--ink);
  }

  .preview-desc {
    margin: 4px 0 0 18px;
    font-size: 12.5px;
    color: var(--ink-tertiary);
    line-height: 1.5;
  }

  .preview-body {
    flex: 1;
    overflow-y: auto;
    padding: 12px 24px 20px;
  }

  .preview-meta-bar {
    font-size: 12.5px;
    color: var(--ink-tertiary);
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--rule-light);
  }

  .empty-preview {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding: 60px 0;
  }

  .empty-preview .empty-icon {
    font-size: 36px;
    margin-bottom: 4px;
  }

  /* ---- 媒体列表 ---- */
  .media-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .media-item {
    display: flex;
    gap: 12px;
    padding: 10px;
    border: 1px solid var(--rule-light);
    border-radius: var(--radius);
    background: var(--bg-surface);
    transition: border-color 200ms;
  }

  .media-item:hover {
    border-color: var(--rule);
  }

  .media-thumb {
    position: relative;
    width: 80px;
    height: 50px;
    border-radius: var(--radius-sm);
    overflow: hidden;
    background: var(--bg-hover);
    flex-shrink: 0;
  }

  .media-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    position: relative;
    z-index: 1;
  }

  .thumb-fallback {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    opacity: 0.4;
  }

  .media-info {
    flex: 1;
    min-width: 0;
  }

  .media-title {
    font-size: 13.5px;
    font-weight: 600;
    color: var(--ink);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    margin-bottom: 4px;
  }

  .media-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 4px;
  }

  .meta-chip {
    display: inline-block;
    padding: 1px 6px;
    border-radius: var(--radius-xs);
    background: var(--bg-hover);
    font-size: 11px;
    color: var(--ink-tertiary);
    font-variant-numeric: tabular-nums;
  }

  .meta-chip.star {
    color: var(--accent2);
  }

  .meta-chip.fav {
    color: #ff3b30;
  }

  .media-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .media-tag {
    display: inline-block;
    padding: 1px 7px;
    border-radius: var(--radius-full);
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 10.5px;
    font-weight: 500;
  }

  .media-tag.more {
    background: var(--bg-hover);
    color: var(--ink-tertiary);
  }

  /* ---- 动画 ---- */
  @keyframes fade-in {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  @keyframes scale-in {
    from { opacity: 0; transform: scale(0.96); }
    to { opacity: 1; transform: scale(1); }
  }

  /* ---- Toast ---- */
  .toast {
    position: fixed;
    bottom: 32px;
    left: 50%;
    transform: translateX(-50%);
    padding: 10px 18px;
    border-radius: var(--radius-full);
    font-size: 13px;
    z-index: 2000;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
    color: #fff;
    animation: toast-in 200ms ease;
  }

  .toast.ok {
    background: var(--ok);
  }

  .toast.err {
    background: #ff3b30;
  }

  @keyframes toast-in {
    from { opacity: 0; transform: translate(-50%, 10px); }
    to { opacity: 1; transform: translate(-50%, 0); }
  }

  /* ---- 响应式 ---- */
  @media (max-width: 640px) {
    .sf-page {
      padding: 16px 14px 32px;
    }

    .page-head {
      flex-direction: column;
      gap: 12px;
    }

    .head-right {
      flex-wrap: wrap;
    }

    .sf-grid {
      grid-template-columns: 1fr;
    }

    .dialog-modal {
      max-width: 100vw;
    }

    .cond-box {
      gap: 6px;
    }

    .sel.dim {
      min-width: 80px;
    }

    .sel.op {
      min-width: 90px;
    }
  }
</style>
