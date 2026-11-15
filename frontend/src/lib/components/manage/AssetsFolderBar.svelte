<script lang="ts">
  // 文件夹层级操作条 — 面包屑 + 新建 / 重命名 / 删除。
  //
  // 重构后这三个操作在 UI 里彻底消失了（原先只在已删除的 FileExplorerView 里），
  // 后端接口一直都在：POST /directories、PUT /directories/rename、DELETE /directories。
  //
  // 安全语义由后端保证（不许越出库根、不许非法目录名、不许删库根），
  // 这里只负责把错误原文展示出来，不自己猜情况。
  import { librariesApi, type Library } from '$lib/api/libraries';
  import { ApiError } from '$lib/api/client';
  import { toasts } from '$lib/stores/toast.svelte';
  import { folderTree } from '$lib/stores/folderTree.svelte';
  import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';

  let {
    libraryId = '',
    dir = '',
    libraries = [],
    onnavigate,
    onchanged
  }: {
    libraryId?: string;
    dir?: string;
    libraries?: Library[];
    onnavigate: (dir: string) => void;
    onchanged: () => void;
  } = $props();

  const library = $derived(libraries.find((l) => String(l.id) === String(libraryId)) ?? null);
  const segments = $derived(dir ? dir.split(/[\\/]/).filter(Boolean) : []);

  // 目录操作内联表单：'none' | 'create' | 'rename'
  let form = $state<'none' | 'create' | 'rename'>('none');
  let inputValue = $state('');
  let busy = $state(false);
  let deleteOpen = $state(false);
  let recursiveOpen = $state(false);

  function joinPath(base: string, name: string): string {
    return base ? `${base}/${name}` : name;
  }

  function parentOf(path: string): string {
    const parts = path.split(/[\\/]/).filter(Boolean);
    parts.pop();
    return parts.join('/');
  }

  function openForm(kind: 'create' | 'rename'): void {
    if (!libraryId) return;
    form = kind;
    inputValue = kind === 'rename' ? (segments[segments.length - 1] ?? '') : '';
  }

  function cancelForm(): void {
    form = 'none';
    inputValue = '';
  }

  function describeError(e: unknown): string {
    if (e instanceof ApiError) {
      const body = e.body as { detail?: unknown } | null | undefined;
      const detail = body?.detail;
      if (typeof detail === 'string' && detail) return detail;
      return e.message;
    }
    return e instanceof Error ? e.message : '操作失败';
  }

  async function submit(): Promise<void> {
    const name = inputValue.trim();
    if (!name || !libraryId || busy) return;
    busy = true;
    try {
      if (form === 'create') {
        const res = await librariesApi.createDirectory(libraryId, dir, name);
        toasts.push(`已创建文件夹「${res.name}」`);
        folderTree.bump();
        onchanged();
      } else {
        const res = await librariesApi.renameDirectory(libraryId, dir, name);
        toasts.push(`已重命名，更新 ${res.updated_media_count} 条媒体路径`);
        folderTree.bump();
        onnavigate(res.new_rel_path);
      }
      cancelForm();
    } catch (e) {
      toasts.push(describeError(e), 'err');
    } finally {
      busy = false;
    }
  }

  async function doDelete(recursive: boolean): Promise<void> {
    if (!libraryId || !dir || busy) return;
    busy = true;
    try {
      const res = await librariesApi.deleteDirectory(libraryId, dir, recursive);
      toasts.push(
        `已删除目录，${res.affected_media_count} 条媒体被标记为文件缺失（记录保留）`
      );
      folderTree.bump();
      const up = parentOf(dir);
      onnavigate(up);
      onchanged();
    } catch (e) {
      // 非空目录：后端 400 + 明确文案 → 升级为递归确认，而不是让用户猜
      const msg = describeError(e);
      if (!recursive && /非空|not empty|400/i.test(msg)) {
        recursiveOpen = true;
      } else {
        toasts.push(msg, 'err');
      }
    } finally {
      busy = false;
    }
  }

  function onFormKeydown(e: KeyboardEvent): void {
    if (e.key === 'Enter') {
      e.preventDefault();
      void submit();
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      cancelForm();
    }
  }
</script>

{#if libraryId}
  <div class="folderbar">
    <div class="crumbs" aria-label="目录位置">
      <button type="button" class="crumb" onclick={() => onnavigate('')} title="库根目录">
        {library?.name ?? '资源库'}
      </button>
      {#each segments as seg, i (i)}
        <span class="sep">›</span>
        <button
          type="button"
          class="crumb"
          class:last={i === segments.length - 1}
          onclick={() => onnavigate(segments.slice(0, i + 1).join('/'))}
        >
          {seg}
        </button>
      {/each}
    </div>

    <div class="actions">
      {#if dir}
        <button type="button" class="fbtn" onclick={() => onnavigate(parentOf(dir))} title="返回上一级">
          ← 上级
        </button>
      {/if}
      <button type="button" class="fbtn" disabled={busy} onclick={() => openForm('create')}>
        ＋ 新建文件夹
      </button>
      {#if dir}
        <button type="button" class="fbtn" disabled={busy} onclick={() => openForm('rename')}>
          重命名
        </button>
        <button type="button" class="fbtn danger" disabled={busy} onclick={() => (deleteOpen = true)}>
          删除目录
        </button>
      {/if}
    </div>
  </div>

  {#if form !== 'none'}
    <div class="formrow">
      <label for="dir-name-input">{form === 'create' ? '新文件夹名' : '新名称'}</label>
      <input
        id="dir-name-input"
        type="text"
        bind:value={inputValue}
        placeholder={form === 'create' ? '例如 2024' : segments[segments.length - 1]}
        onkeydown={onFormKeydown}
      />
      <button type="button" class="fbtn primary" disabled={busy || !inputValue.trim()} onclick={() => void submit()}>
        {busy ? '处理中…' : '确定'}
      </button>
      <button type="button" class="fbtn" onclick={cancelForm}>取消</button>
    </div>
  {/if}

  <ConfirmDialog
    bind:open={deleteOpen}
    title="删除目录"
    description={`将删除磁盘目录「${dir}」。目录里的媒体记录会保留，但会被标记为「文件缺失」（可到「文件缺失」视图查看）。`}
    confirmText="删除"
    danger
    onconfirm={() => {
      deleteOpen = false;
      void doDelete(false);
    }}
  />

  <ConfirmDialog
    bind:open={recursiveOpen}
    title="目录非空"
    description={`「${dir}」里还有文件。递归删除会连同其中的媒体文件一起从磁盘删除（记录仍保留并标记为文件缺失）。`}
    confirmText="递归删除"
    danger
    onconfirm={() => {
      recursiveOpen = false;
      void doDelete(true);
    }}
  />
{/if}

<style>
  .folderbar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 16px 0;
    font-size: 12.5px;
    flex-wrap: wrap;
  }
  .crumbs {
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
    overflow: hidden;
  }
  .crumb {
    font: inherit;
    font-size: 12.5px;
    padding: 2px 6px;
    border: 1px solid transparent;
    border-radius: var(--radius-xs);
    background: transparent;
    color: var(--ink-secondary);
    cursor: pointer;
    white-space: nowrap;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .crumb:hover {
    background: var(--bg-hover);
    color: var(--ink);
  }
  .crumb.last {
    color: var(--ink);
    font-weight: 600;
  }
  .sep {
    color: var(--ink-faint);
  }
  .actions {
    display: flex;
    gap: 6px;
    margin-left: auto;
  }
  .fbtn {
    font: inherit;
    font-size: 12px;
    padding: 4px 10px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
    color: var(--ink-secondary);
    cursor: pointer;
    white-space: nowrap;
  }
  .fbtn:hover:not(:disabled) {
    color: var(--ink);
    border-color: var(--ink-faint);
  }
  .fbtn.primary {
    border-color: var(--accent);
    color: var(--accent);
  }
  .fbtn.danger {
    color: var(--danger);
    border-color: color-mix(in srgb, var(--danger) 45%, transparent);
  }
  .fbtn:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .formrow {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px 0;
    font-size: 12.5px;
    color: var(--ink-secondary);
  }
  .formrow input {
    font: inherit;
    font-size: 12.5px;
    padding: 5px 9px;
    min-width: 180px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--accent);
    background: var(--bg-elevated);
    color: var(--ink);
  }
  .formrow input:focus {
    outline: none;
  }
</style>
