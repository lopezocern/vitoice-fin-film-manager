<script lang="ts">
  import { client, BASE_URL, ApiError } from '$lib/api/client';
  import { mediaApi, type Media, isAvMedia } from '$lib/api/media';

  // 从任意异常中提取可读信息：后端 detail 优先，其次 message，最后兜底文案。
  // 修复：旧逻辑非 ApiError 一律显示"请检查后端服务"，掩盖了真实原因（网络
  // 错误、JSON 解析失败等），导致问题无法定位。
  function extractError(e: unknown, fallback: string): string {
    if (e instanceof ApiError) {
      const body = e.body as { detail?: unknown } | null | undefined;
      const detail = body?.detail;
      if (typeof detail === 'string' && detail) return detail;
      if (typeof detail === 'object' && detail !== null) {
        try {
          return JSON.stringify(detail);
        } catch {
          /* ignore */
        }
      }
      return e.message || fallback;
    }
    if (e instanceof Error && e.message) return e.message;
    return fallback;
  }

  let {
    open = $bindable(false),
    media,
    onsuccess
  }: {
    open: boolean;
    media: Media | null;
    onsuccess?: () => void;
  } = $props();

  let title = $state('');
  let year = $state('');
  let description = $state('');
  let posterUrl = $state('');
  let posterPreview = $state('');
  let uploading = $state(false);
  let saving = $state(false);
  let error = $state<string | null>(null);
  let fileInput = $state<HTMLInputElement | null>(null);

  // Sync form fields when dialog opens or media changes
  $effect(() => {
    if (open && media) {
      title = media.title ?? '';
      year = media.year ? String(media.year) : '';
      description = media.description ?? '';
      posterUrl = media.poster
        ? `${BASE_URL}/media/${media.id}/poster?t=${Date.now()}`
        : media.thumbnail
          ? `${BASE_URL}/media/${media.id}/thumbnail?t=${Date.now()}`
          : '';
      posterPreview = '';
      error = null;
    }
  });

  const isAv = $derived(media ? isAvMedia(media) : false);

  function handleFileSelect(e: Event): void {
    const input = e.target as HTMLInputElement;
    if (!input.files?.[0]) return;
    const file = input.files[0];

    // Validate image type
    if (!file.type.startsWith('image/')) {
      error = '请选择图片文件';
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      error = '图片大小不能超过 10MB';
      return;
    }

    // Preview
    const reader = new FileReader();
    reader.onload = () => {
      posterPreview = reader.result as string;
    };
    reader.readAsDataURL(file);
    error = null;
  }

  async function uploadPoster(): Promise<boolean> {
    if (!media || !fileInput?.files?.[0]) return true;
    uploading = true;
    try {
      const formData = new FormData();
      formData.append('file', fileInput.files[0]);
      const resp = await fetch(`${BASE_URL}/media/${media.id}/poster`, {
        method: 'POST',
        body: formData,
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || '封面上传失败');
      }
      return true;
    } catch (e) {
      error = e instanceof Error ? e.message : '封面上传失败';
      return false;
    } finally {
      uploading = false;
    }
  }

  async function deletePoster(): Promise<void> {
    if (!media) return;
    try {
      await client.delete(`/media/${media.id}/poster`);
      posterUrl = '';
      posterPreview = '';
      if (fileInput) fileInput.value = '';
    } catch (e) {
      error = extractError(e, '删除封面失败');
    }
  }

  async function handleSave(): Promise<void> {
    if (!media) return;
    saving = true;
    error = null;
    try {
      // Upload poster first if a new file is selected
      if (fileInput?.files?.[0]) {
        const ok = await uploadPoster();
        if (!ok) {
          saving = false;
          return;
        }
      }

      // Save metadata
      // 防御：year/title/description 用 String() 包裹后再 trim，避免任何
      // 非字符串值（如 number/undefined）触发 "xxx.trim is not a function"。
      const payload: Record<string, unknown> = {};
      const titleVal = String(title ?? '').trim();
      const yearVal = String(year ?? '').trim();
      const descVal = String(description ?? '').trim();
      if (titleVal !== (media.title ?? '')) payload.title = titleVal;
      const yearNum = yearVal ? parseInt(yearVal, 10) : undefined;
      if (yearNum !== media.year) payload.year = yearNum ?? null;
      if (descVal !== (media.description ?? '')) payload.description = descVal || null;

      if (Object.keys(payload).length > 0) {
        await client.put(`/media/${media.id}`, payload);
      }

      open = false;
      onsuccess?.();
    } catch (e) {
      // 透传真实错误信息（含后端 detail），避免统一文案掩盖根因
      error = extractError(e, '保存失败，请检查后端服务');
    } finally {
      saving = false;
    }
  }
</script>

{#if open && media}
  <div class="modal-overlay" onclick={() => !saving && !uploading && (open = false)}>
    <div class="modal-card" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h2>编辑媒体</h2>
        <button class="close-btn" onclick={() => (open = false)} disabled={saving || uploading}>✕</button>
      </div>
      <div class="modal-body">
        {#if error}<div class="error-banner">{error}</div>{/if}

        <!-- 封面图 -->
        <div class="poster-section">
          <label class="form-label" for="poster-file-input">封面图</label>
          <div class="poster-preview-area" class:av-poster={isAv}>
            {#if posterPreview}
              <img src={posterPreview} alt="新封面预览" class="poster-img" />
            {:else if posterUrl}
              <img src={posterUrl} alt="当前封面" class="poster-img" />
            {:else}
              <div class="poster-placeholder">
                <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" opacity="0.3">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                  <circle cx="8.5" cy="8.5" r="1.5"/>
                  <polyline points="21 15 16 10 5 21"/>
                </svg>
                <span>暂无封面</span>
              </div>
            {/if}
          </div>
          <div class="poster-actions">
            <button class="btn-secondary" onclick={() => fileInput?.click()} disabled={uploading || saving}>
              {uploading ? '上传中…' : '选择图片'}
            </button>
            {#if (posterUrl || posterPreview) && !uploading}
              <button class="btn-danger" onclick={deletePoster} disabled={saving}>删除封面</button>
            {/if}
            <input
              id="poster-file-input"
              bind:this={fileInput}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              onchange={handleFileSelect}
              style="display:none"
            />
          </div>
          <div class="form-hint">支持 JPG/PNG/WebP，最大 10MB</div>
        </div>

        <!-- 标题 -->
        <div class="form-group">
          <label class="form-label" for="edit-title">标题</label>
          <input id="edit-title" type="text" bind:value={title} placeholder="媒体标题" disabled={saving} />
        </div>

        <!-- 年份 -->
        <div class="form-group">
          <label class="form-label" for="edit-year">年份</label>
          <input id="edit-year" type="number" bind:value={year} placeholder="如 2024" min="1900" max="2099" disabled={saving} />
        </div>

        <!-- 描述 -->
        <div class="form-group">
          <label class="form-label" for="edit-desc">描述</label>
          <textarea id="edit-desc" bind:value={description} placeholder="媒体描述" rows="3" disabled={saving}></textarea>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick={() => (open = false)} disabled={saving || uploading}>取消</button>
        <button class="btn-primary" onclick={handleSave} disabled={saving || uploading}>
          {saving ? '保存中…' : '保存'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000; }
  .modal-card { background: var(--bg-elevated, #1e1e2e); border: 1px solid var(--border, rgba(255,255,255,0.1)); border-radius: 12px; width: 560px; max-width: 90vw; max-height: 85vh; display: flex; flex-direction: column; }
  .modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(255,255,255,0.1)); }
  .modal-header h2 { font-size: 16px; font-weight: 600; margin: 0; }
  .close-btn { background: none; border: none; color: var(--text-muted, #888); cursor: pointer; font-size: 18px; padding: 4px 8px; border-radius: 6px; }
  .close-btn:hover { background: rgba(255,255,255,0.1); }
  .modal-body { padding: 20px; overflow-y: auto; flex: 1; }
  .form-group { margin-bottom: 16px; }
  .form-label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 6px; }
  .form-group input, .form-group textarea { width: 100%; padding: 8px 12px; background: var(--bg-surface, #2a2a3a); border: 1px solid var(--border, rgba(255,255,255,0.1)); border-radius: 8px; color: var(--text, #fff); font-size: 14px; outline: none; box-sizing: border-box; resize: vertical; }
  .form-group input:focus, .form-group textarea:focus { border-color: var(--accent, #7c3aed); }
  .form-hint { font-size: 12px; color: var(--text-muted, #888); margin-top: 4px; }
  .error-banner { background: rgba(239,68,68,0.15); color: #f87171; padding: 8px 12px; border-radius: 8px; font-size: 13px; margin-bottom: 16px; }
  .modal-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 16px 20px; border-top: 1px solid var(--border, rgba(255,255,255,0.1)); }

  .poster-section { margin-bottom: 20px; }
  .poster-preview-area { width: 100%; height: 200px; background: var(--bg-surface, #2a2a3a); border: 1px solid var(--border, rgba(255,255,255,0.1)); border-radius: 8px; display: flex; align-items: center; justify-content: center; overflow: hidden; margin-bottom: 8px; }
  .poster-preview-area.av-poster { height: 140px; }
  .poster-img { max-width: 100%; max-height: 100%; object-fit: contain; }
  .poster-placeholder { display: flex; flex-direction: column; align-items: center; gap: 8px; color: var(--text-muted, #888); font-size: 13px; }
  .poster-actions { display: flex; gap: 8px; align-items: center; }

  .btn-primary, .btn-secondary, .btn-danger { padding: 8px 16px; border-radius: 8px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s; }
  .btn-primary { background: var(--accent, #7c3aed); color: #fff; border: none; }
  .btn-primary:hover:not(:disabled) { background: var(--accent-hover, #6d28d9); }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-secondary { background: transparent; color: var(--text-muted, #888); border: 1px solid var(--border, rgba(255,255,255,0.1)); }
  .btn-secondary:hover:not(:disabled) { background: rgba(255,255,255,0.05); }
  .btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-danger { background: transparent; color: #f87171; border: 1px solid rgba(239,68,68,0.3); }
  .btn-danger:hover:not(:disabled) { background: rgba(239,68,68,0.1); }
  .btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
