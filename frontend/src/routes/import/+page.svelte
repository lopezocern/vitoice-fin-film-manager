<script lang="ts">
  // 导入向导：4 步流程引导首次用户创建库、扫描、生成缩略图、查看结果
  // 使用 client 直接与后端交互（库的完整字段含 scrape_mode / watch_enabled）
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { client, ApiError } from '$lib/api/client';
  import { tasksApi, type Task } from '$lib/api/tasks';
  import { formatNumber } from '$lib/utils/format';
  import { librariesStore } from '$lib/stores/libraries.svelte';

  // ---- 库完整类型（后端 LibraryResponse 比前端 libraries.ts 更丰富） ----
  interface LibraryFull {
    id: number;
    name: string;
    type: string;
    root_path: string;
    scrape_mode: string;
    is_restricted: boolean;
    watch_enabled: boolean;
    auto_import: boolean;
    auto_mark_missing: boolean;
    description: string | null;
    color: string | null;
    sort_order: number;
    created_at: string;
    updated_at: string;
    media_count: number;
  }

  type Step = 0 | 1 | 2 | 3;
  type ScrapeMode = 'none' | 'movie' | 'tv' | 'av' | 'custom';

  let step = $state<Step>(0);
  let creating = $state(false);
  let transitioning = $state(false);
  let errorMsg = $state<string | null>(null);

  // 步骤 1 表单
  let libName = $state('');
  let libPath = $state('');
  let scrapeMode = $state<ScrapeMode>('none');
  let watchEnabled = $state(true);
  let isRestricted = $state(false);
  let picking = $state(false);

  // AV 刮削模式首次选择时自动标记为限制内容（仅触发一次，不覆盖用户后续手动修改）
  let _avAutoToggled = false;
  $effect(() => {
    if (scrapeMode === 'av' && !_avAutoToggled) {
      isRestricted = true;
      _avAutoToggled = true;
    }
  });

  // 已创建的库
  let createdLib = $state<LibraryFull | null>(null);

  // 步骤 2 / 3 任务进度
  let scanTask = $state<Task | null>(null);
  let thumbTask = $state<Task | null>(null);
  let polling = $state(false);
  let pollKind: 'scan' | 'thumbnail' | null = null;
  // generation 用于使旧的轮询 tick 自动失效，防止 scan→thumbnail 切换时旧 tick 继续运行
  let pollGeneration = 0;
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  let thumbSkipTimer: ReturnType<typeof setTimeout> | null = null;
  let scanStartedAt = 0;

  // 步骤 4 统计
  let allLibs = $state<LibraryFull[]>([]);
  let totalFiles = $state(0);

  // toast
  let toast = $state<string | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;
  function showToast(msg: string): void {
    toast = msg;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2800);
  }

  const steps = [
    { label: '创建库' },
    { label: '扫描' },
    { label: '缩略图' },
    { label: '完成' }
  ];

  const scrapeOptions: { value: ScrapeMode; label: string; desc: string }[] = [
    { value: 'none', label: '不刮削', desc: '仅扫描文件，不获取元数据' },
    { value: 'movie', label: '电影', desc: '按电影规则刮削元数据' },
    { value: 'tv', label: '电视剧', desc: '按剧集规则刮削元数据' },
    { value: 'av', label: '限制内容', desc: '按限制内容规则刮削元数据' },
    { value: 'custom', label: '自定义', desc: '使用自定义刮削规则' }
  ];

  const canProceedStep0 = $derived(libName.trim().length > 0 && libPath.trim().length > 0);

  // ---- 目录选择（Tauri dialog） ----
  async function pickDirectory(): Promise<void> {
    picking = true;
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ directory: true, multiple: false, title: '选择资源库目录' });
      if (typeof selected === 'string' && selected) {
        libPath = selected;
      }
    } catch {
      showToast('无法打开目录选择器，请手动输入路径');
    } finally {
      picking = false;
    }
  }

  // ---- 步骤 1：创建库 ----
  async function createLibrary(): Promise<void> {
    if (creating || transitioning) return;
    creating = true;
    errorMsg = null;
    try {
      const lib = await client.post<LibraryFull>('/libraries', {
        name: libName.trim(),
        type: 'video',
        root_path: libPath.trim(),
        scrape_mode: scrapeMode,
        is_restricted: isRestricted,
        watch_enabled: watchEnabled,
        auto_import: true,
        auto_mark_missing: true,
        description: ''
      });
      createdLib = lib;
      // 通知共享 store 立即刷新侧边栏
      librariesStore.reload();
      // 清理可能残留的轮询状态再切换步骤
      stopPolling();
      step = 1;
      startScan();
    } catch (e) {
      errorMsg = e instanceof ApiError ? `创建库失败：${e.status}` : '创建库失败，请检查后端服务';
    } finally {
      creating = false;
    }
  }

  // ---- 步骤 2：触发扫描并轮询任务 ----
  async function startScan(): Promise<void> {
    if (!createdLib) return;
    scanStartedAt = Date.now();
    scanTask = null;
    try {
      await client.post(`/libraries/${createdLib.id}/scan`);
    } catch {
      // 扫描触发失败不阻塞，仍尝试轮询
    }
    startPolling('scan');
  }

  function startPolling(kind: 'scan' | 'thumbnail'): void {
    // 先取消已有的轮询定时器（不触碰 thumbSkipTimer，它由 startThumbnail 管理）
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    polling = true;
    pollKind = kind;
    // 每次启动轮询递增 generation，旧的 tick 通过 generation 比对自动失效
    const generation = ++pollGeneration;
    const tick = async () => {
      if (generation !== pollGeneration) return;
      await refreshTask(kind, generation);
      if (generation !== pollGeneration) return;
      pollTimer = setTimeout(tick, 1500);
    };
    tick();
  }

  function stopPolling(): void {
    polling = false;
    pollKind = null;
    // 递增 generation 使所有进行中的旧 tick 失效
    pollGeneration++;
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    if (thumbSkipTimer) {
      clearTimeout(thumbSkipTimer);
      thumbSkipTimer = null;
    }
  }

  // 扫描进行中若离开 /import，tick 的 setTimeout 自续链永远不会停：
  // pollGeneration 不再被递增，旧 tick 一直写已销毁组件的 $state。
  onDestroy(stopPolling);

  async function refreshTask(kind: 'scan' | 'thumbnail', generation: number): Promise<void> {
    if (generation !== pollGeneration) return;
    try {
      const tasks = await tasksApi.list({ type: kind });
      // await 返回后再次校验，防止期间被 stopPolling / startPolling 取代
      if (generation !== pollGeneration) return;
      const running = (tasks ?? []).find(
        (t) => t.status === 'running' || t.status === 'pending'
      );
      const latest = running ?? (tasks ?? [])[0];
      if (kind === 'scan') {
        scanTask = latest ?? null;
        // 扫描完成或无可追踪任务
        if (latest && (latest.status === 'completed' || latest.status === 'failed' || latest.status === 'cancelled')) {
          if (latest.status === 'completed') {
            // 扫描成功 → 自动进入缩略图步骤
            stopPolling();
            step = 2;
            startThumbnail();
          } else {
            // 扫描失败/取消，停止轮询，留在当前步骤等待用户操作
            stopPolling();
          }
        } else if (!latest && Date.now() - scanStartedAt > 4000) {
          // 后端任务系统尚未接入，允许手动继续
          stopPolling();
        }
      } else {
        thumbTask = latest ?? null;
        if (latest && (latest.status === 'completed' || latest.status === 'failed' || latest.status === 'cancelled')) {
          stopPolling();
          if (latest.status === 'completed' || latest.status === 'failed') {
            // 缩略图完成 → 自动进入完成步骤
            // 加 transitioning 防止与手动跳过/返回产生竞争
            if (transitioning) return;
            transitioning = true;
            try {
              await loadStats();
              step = 3;
            } finally {
              transitioning = false;
            }
          }
        }
      }
    } catch {
      // 忽略轮询错误
    }
  }

  // ---- 步骤 3：缩略图（依赖扫描完成，这里直接进入统计） ----
  async function startThumbnail(): Promise<void> {
    // 清理可能残留的跳过定时器，防止旧定时器误停新轮询
    if (thumbSkipTimer) {
      clearTimeout(thumbSkipTimer);
      thumbSkipTimer = null;
    }
    thumbTask = null;
    startPolling('thumbnail');
    // 若短时间内无缩略图任务，停止轮询以节省资源（用户仍可手动"下一步"）
    thumbSkipTimer = setTimeout(() => {
      // 仅在仍在缩略图步骤、轮询类型仍为 thumbnail 且未发现任务时触发
      if (step === 2 && pollKind === 'thumbnail' && !thumbTask) {
        stopPolling();
      }
    }, 5000);
  }

  async function skipToStats(): Promise<void> {
    if (transitioning) return;
    transitioning = true;
    stopPolling();
    try {
      await loadStats();
      step = 3;
    } finally {
      transitioning = false;
    }
  }

  // ---- 步骤 4：统计 ----
  async function loadStats(): Promise<void> {
    try {
      const libs = await client.get<LibraryFull[]>('/libraries');
      allLibs = libs ?? [];
      totalFiles = allLibs.reduce((s, l) => s + (l.media_count ?? 0), 0);
      // 总大小需从媒体接口聚合，此处用库数量与媒体数展示
      try {
        const res = await client.get<{ total: number }>('/media', { page: 1, page_size: 1 });
        totalFiles = res?.total ?? totalFiles;
      } catch {
        // 忽略
      }
    } catch {
      // 忽略
    }
  }

  // ---- 导航 ----
  function goToMedia(): void {
    goto('/media');
  }

  function createAnother(): void {
    if (transitioning) return;
    stopPolling();
    step = 0;
    libName = '';
    libPath = '';
    scrapeMode = 'none';
    watchEnabled = true;
    isRestricted = false;
    createdLib = null;
    scanTask = null;
    thumbTask = null;
    errorMsg = null;
  }

  function backToStep0(): void {
    if (transitioning) return;
    stopPolling();
    step = 0;
  }

  function backToStep1(): void {
    if (transitioning) return;
    stopPolling();
    step = 1;
  }

  // 进度派生
  const scanProgress = $derived(scanTask ? scanTask.progress : 0);
  const thumbProgress = $derived(thumbTask ? thumbTask.progress : 0);

  onMount(() => {
    return () => {
      stopPolling();
      if (toastTimer) clearTimeout(toastTimer);
    };
  });
</script>

<svelte:head><title>导入向导 — vitoice</title></svelte:head>

<div class="wizard-page">
  <div class="wizard-card">
    <!-- 步骤指示器 -->
    <div class="stepper">
      {#each steps as s, i (i)}
        <div class="step" class:done={i < step} class:active={i === step}>
          <div class="dot">
            {#if i < step}
              <svg viewBox="0 0 24 24" width="14" height="14"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" fill="currentColor"/></svg>
            {:else}
              <span>{i + 1}</span>
            {/if}
          </div>
          <span class="step-label">{s.label}</span>
        </div>
        {#if i < steps.length - 1}
          <div class="step-line" class:done={i < step}></div>
        {/if}
      {/each}
    </div>

    <!-- 步骤内容 -->
    <div class="step-body">
      {#if step === 0}
        <!-- 步骤 1：欢迎 / 创建库 -->
        <div class="step-content">
          <div class="welcome">
            <h1>欢迎使用 vitoice</h1>
            <p>让我们创建第一个资源库，开始管理你的媒体文件。</p>
          </div>

          <div class="form-group">
            <label for="lib-name">库名称</label>
            <input
              id="lib-name"
              type="text"
              placeholder="例如：我的视频库"
              bind:value={libName}
            />
          </div>

          <div class="form-group">
            <label for="lib-path">目录路径</label>
            <div class="path-row">
              <input
                id="lib-path"
                type="text"
                placeholder="选择或输入目录路径"
                bind:value={libPath}
              />
              <button class="pick-btn" onclick={pickDirectory} disabled={picking}>
                {picking ? '选择中…' : '浏览…'}
              </button>
            </div>
            <span class="hint">vitoice 将扫描该目录下的所有媒体文件</span>
          </div>

          <div class="form-group">
            <span class="field-label">刮削模式</span>
            <div class="scrape-grid">
              {#each scrapeOptions as o (o.value)}
                <button
                  type="button"
                  class="scrape-card"
                  class:active={scrapeMode === o.value}
                  onclick={() => (scrapeMode = o.value)}
                >
                  <span class="scrape-label">{o.label}</span>
                  <span class="scrape-desc">{o.desc}</span>
                </button>
              {/each}
            </div>
          </div>

          <div class="form-group toggle-row">
            <div class="toggle-info">
              <span class="toggle-label">启用文件监控</span>
              <span class="hint">目录变化时自动更新媒体记录</span>
            </div>
            <button
              type="button"
              class="toggle"
              class:on={watchEnabled}
              onclick={() => (watchEnabled = !watchEnabled)}
              role="switch"
              aria-checked={watchEnabled}
            >
              <span class="knob"></span>
            </button>
          </div>

          <div class="form-group toggle-row">
            <div class="toggle-info">
              <span class="toggle-label">限制内容</span>
              <span class="hint">标记为限制的库在「显示限制内容」关闭时隐藏（选择限制内容模式时自动开启）</span>
            </div>
            <button
              type="button"
              class="toggle"
              class:on={isRestricted}
              onclick={() => (isRestricted = !isRestricted)}
              role="switch"
              aria-checked={isRestricted}
            >
              <span class="knob"></span>
            </button>
          </div>

          {#if errorMsg}
            <div class="error-banner">{errorMsg}</div>
          {/if}
        </div>
      {:else if step === 1}
        <!-- 步骤 2：扫描中 -->
        <div class="step-content">
          <div class="welcome">
            <h1>正在扫描库</h1>
            <p>{createdLib?.name ?? ''} · {createdLib?.root_path ?? ''}</p>
          </div>

          <div class="progress-block">
            <div class="progress-icon scanning">
              <svg viewBox="0 0 24 24" width="40" height="40" class="spin">
                <path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 14.97 20 13.54 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 9.03 4 10.46 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z" fill="currentColor"/>
              </svg>
            </div>
            <div class="progress-stats">
              {#if scanTask}
                <div class="stat-line">
                  <span class="stat-label">已发现</span>
                  <span class="stat-value">{formatNumber(scanTask.total)}</span>
                </div>
                <div class="stat-line">
                  <span class="stat-label">已处理</span>
                  <span class="stat-value">{formatNumber(scanTask.current)}</span>
                </div>
                <div class="progress-track">
                  <div class="progress-fill" style={`width:${scanProgress}%`}></div>
                </div>
                <div class="progress-meta">
                  <span>{scanProgress}%</span>
                  <span class="muted">{scanTask.message ?? '扫描中…'}</span>
                </div>
              {:else}
                <div class="stat-line">
                  <span class="stat-label">扫描任务已派发</span>
                </div>
                <div class="progress-track">
                  <div class="progress-fill indeterminate"></div>
                </div>
                <div class="progress-meta">
                  <span class="muted">等待任务进度…</span>
                </div>
              {/if}
            </div>
          </div>

          <div class="skip-note">
            扫描在后台进行，你可以等待完成或
            <button class="link-btn" onclick={skipToStats}>直接查看结果</button>
          </div>
        </div>
      {:else if step === 2}
        <!-- 步骤 3：缩略图生成 -->
        <div class="step-content">
          <div class="welcome">
            <h1>生成缩略图</h1>
            <p>扫描完成，正在为媒体生成缩略图。</p>
          </div>

          <div class="progress-block">
            <div class="progress-icon">
              <svg viewBox="0 0 24 24" width="40" height="40">
                <path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z" fill="currentColor"/>
              </svg>
            </div>
            <div class="progress-stats">
              {#if thumbTask}
                <div class="stat-line">
                  <span class="stat-label">已生成</span>
                  <span class="stat-value">{formatNumber(thumbTask.current)} / {formatNumber(thumbTask.total)}</span>
                </div>
                <div class="progress-track">
                  <div class="progress-fill" style={`width:${thumbProgress}%`}></div>
                </div>
                <div class="progress-meta">
                  <span>{thumbProgress}%</span>
                  <span class="muted">{thumbTask.message ?? '生成中…'}</span>
                </div>
              {:else}
                <div class="stat-line">
                  <span class="stat-label">等待缩略图任务</span>
                </div>
                <div class="progress-track">
                  <div class="progress-fill indeterminate"></div>
                </div>
                <div class="progress-meta">
                  <span class="muted">缩略图将在扫描后自动生成</span>
                </div>
              {/if}
            </div>
          </div>

          <div class="skip-note">
            <button class="link-btn" onclick={skipToStats}>跳过并查看结果</button>
          </div>
        </div>
      {:else}
        <!-- 步骤 4：完成 -->
        <div class="step-content">
          <div class="welcome center">
            <div class="done-icon">
              <svg viewBox="0 0 24 24" width="48" height="48">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="currentColor"/>
              </svg>
            </div>
            <h1>导入完成</h1>
            <p>你的资源库已就绪，可以开始浏览和管理了。</p>
          </div>

          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-num">{formatNumber(totalFiles)}</div>
              <div class="stat-name">媒体文件</div>
            </div>
            <div class="stat-card">
              <div class="stat-num">{formatNumber(allLibs.length)}</div>
              <div class="stat-name">资源库</div>
            </div>
            <div class="stat-card">
              <div class="stat-num">{scrapeMode === 'none' ? '—' : scrapeOptions.find((o) => o.value === scrapeMode)?.label ?? '—'}</div>
              <div class="stat-name">刮削模式</div>
            </div>
          </div>

          {#if allLibs.length > 0}
            <div class="lib-summary">
              <div class="summary-title">资源库列表</div>
              {#each allLibs as lib (lib.id)}
                <div class="summary-row">
                  <span class="summary-name">{lib.name}</span>
                  <span class="summary-path muted">{lib.root_path}</span>
                  <span class="summary-count">{formatNumber(lib.media_count ?? 0)} 项</span>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      {/if}
    </div>

    <!-- 底部按钮 -->
    <div class="wizard-foot">
      {#if step === 0}
        <span></span>
        <button class="btn btn-primary" onclick={createLibrary} disabled={!canProceedStep0 || creating || transitioning}>
          {creating ? '创建中…' : '下一步'}
        </button>
      {:else if step === 1}
        <button class="btn btn-ghost" onclick={backToStep0} disabled={transitioning}>上一步</button>
        <button class="btn btn-primary" onclick={skipToStats} disabled={transitioning}>下一步</button>
      {:else if step === 2}
        <button class="btn btn-ghost" onclick={backToStep1} disabled={transitioning}>上一步</button>
        <button class="btn btn-primary" onclick={skipToStats} disabled={transitioning}>下一步</button>
      {:else}
        <button class="btn btn-ghost" onclick={createAnother}>再创建一个库</button>
        <button class="btn btn-primary" onclick={goToMedia}>前往媒体页</button>
      {/if}
    </div>
  </div>
</div>

{#if toast}
  <div class="toast">{toast}</div>
{/if}

<style>
  .wizard-page {
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 40px 24px;
    overflow-y: auto;
    flex: 1;
    min-height: 0;
  }

  .wizard-card {
    width: 100%;
    max-width: 600px;
    background: var(--bg-elevated);
    border: 1px solid var(--rule);
    border-radius: var(--radius-lg);
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ---- 步骤指示器 ---- */
  .stepper {
    display: flex;
    align-items: center;
    padding: 24px 32px 20px;
    border-bottom: 1px solid var(--rule);
    background: var(--bg-surface);
  }

  .step {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }

  .dot {
    width: 28px;
    height: 28px;
    border-radius: var(--radius-full);
    background: var(--bg-elevated);
    border: 2px solid var(--rule);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--ink-tertiary);
    font-size: 12.5px;
    font-weight: 600;
    transition: all 200ms ease;
  }

  .step.active .dot {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
    box-shadow: 0 0 0 4px var(--accent-soft);
  }

  .step.done .dot {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .step-label {
    font-size: 12px;
    color: var(--ink-tertiary);
    transition: color 200ms;
  }

  .step.active .step-label {
    color: var(--ink);
    font-weight: 600;
  }

  .step-line {
    flex: 1;
    height: 2px;
    background: var(--rule);
    margin: 0 8px;
    margin-bottom: 20px;
    transition: background 200ms;
  }

  .step-line.done {
    background: var(--accent);
  }

  /* ---- 步骤内容 ---- */
  .step-body {
    flex: 1;
    padding: 28px 32px;
    min-height: 280px;
  }

  .welcome h1 {
    margin: 0 0 6px;
    font-size: 22px;
    font-weight: 700;
    color: var(--ink);
    letter-spacing: 0;
  }

  .welcome p {
    margin: 0 0 24px;
    font-size: 13px;
    color: var(--ink-tertiary);
  }

  .welcome.center {
    text-align: center;
  }

  .done-icon {
    color: var(--ok);
    margin-bottom: 8px;
  }

  /* ---- 表单 ---- */
  .form-group {
    margin-bottom: 20px;
  }

  .form-group label,
  .form-group .field-label {
    display: block;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--ink);
    margin-bottom: 8px;
  }

  .form-group input[type='text'] {
    width: 100%;
    height: 38px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 13.5px;
    font-family: inherit;
    transition: border-color 200ms;
  }

  .form-group input[type='text']:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .path-row {
    display: flex;
    gap: 8px;
  }

  .path-row input {
    flex: 1;
  }

  .pick-btn {
    height: 38px;
    padding: 0 14px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-surface);
    color: var(--ink);
    font-size: 13px;
    font-weight: 500;
    transition: all 200ms ease;
    white-space: nowrap;
  }

  .pick-btn:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
  }

  .pick-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .hint {
    display: block;
    margin-top: 6px;
    font-size: 11.5px;
    color: var(--ink-tertiary);
  }

  /* ---- 刮削模式 ---- */
  .scrape-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 8px;
  }

  .scrape-card {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 10px 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    text-align: left;
    transition: all 200ms ease;
    cursor: pointer;
  }

  .scrape-card:hover {
    border-color: var(--ink-tertiary);
  }

  .scrape-card.active {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .scrape-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
  }

  .scrape-card.active .scrape-label {
    color: var(--accent);
  }

  .scrape-desc {
    font-size: 11px;
    color: var(--ink-tertiary);
    line-height: 1.4;
  }

  /* ---- 开关 ---- */
  .toggle-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .toggle-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .toggle-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
  }

  .toggle {
    width: 42px;
    height: 24px;
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
    width: 20px;
    height: 20px;
    border-radius: var(--radius-full);
    background: #fff;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
    transition: transform 200ms ease;
  }

  .toggle.on .knob {
    transform: translateX(18px);
  }

  .error-banner {
    margin-top: 4px;
    padding: 10px 12px;
    background: var(--accent2-soft);
    border: 1px solid var(--accent2);
    border-radius: var(--radius);
    color: var(--accent2);
    font-size: 12.5px;
  }

  /* ---- 进度块 ---- */
  .progress-block {
    display: flex;
    gap: 20px;
    align-items: flex-start;
    padding: 24px;
    background: var(--bg-surface);
    border-radius: var(--radius-lg);
  }

  .progress-icon {
    width: 64px;
    height: 64px;
    border-radius: var(--radius-full);
    background: var(--accent-soft);
    color: var(--accent);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .progress-icon.scanning {
    color: var(--accent);
  }

  .spin {
    animation: spin 1.4s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .progress-stats {
    flex: 1;
    min-width: 0;
  }

  .stat-line {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 8px;
  }

  .stat-label {
    font-size: 12.5px;
    color: var(--ink-tertiary);
  }

  .stat-value {
    font-size: 18px;
    font-weight: 700;
    color: var(--ink);
    font-variant-numeric: tabular-nums;
  }

  .progress-track {
    height: 8px;
    background: var(--rule);
    border-radius: var(--radius-full);
    overflow: hidden;
    margin-bottom: 8px;
  }

  .progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: var(--radius-full);
    transition: width 400ms ease;
  }

  .progress-fill.indeterminate {
    width: 40%;
    animation: indet 1.4s ease-in-out infinite;
  }

  @keyframes indet {
    0% {
      margin-left: -40%;
    }
    100% {
      margin-left: 100%;
    }
  }

  .progress-meta {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--ink-tertiary);
  }

  .muted {
    color: var(--ink-tertiary);
  }

  .skip-note {
    margin-top: 16px;
    font-size: 12.5px;
    color: var(--ink-tertiary);
    text-align: center;
  }

  .link-btn {
    background: none;
    border: none;
    color: var(--accent);
    font-size: 12.5px;
    padding: 0 4px;
    cursor: pointer;
    transition: opacity 200ms;
  }

  .link-btn:hover {
    opacity: 0.7;
  }

  /* ---- 统计 ---- */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-bottom: 24px;
  }

  .stat-card {
    padding: 20px 12px;
    background: var(--bg-surface);
    border-radius: var(--radius);
    text-align: center;
  }

  .stat-num {
    font-size: 26px;
    font-weight: 700;
    color: var(--accent);
    font-variant-numeric: tabular-nums;
    margin-bottom: 4px;
  }

  .stat-name {
    font-size: 12px;
    color: var(--ink-tertiary);
  }

  .lib-summary {
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    overflow: hidden;
  }

  .summary-title {
    padding: 10px 14px;
    background: var(--bg-surface);
    font-size: 12px;
    font-weight: 600;
    color: var(--ink-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .summary-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border-top: 1px solid var(--rule);
    font-size: 13px;
  }

  .summary-row:first-of-type {
    border-top: none;
  }

  .summary-name {
    font-weight: 600;
    color: var(--ink);
  }

  .summary-path {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 12px;
  }

  .summary-count {
    color: var(--ink-tertiary);
    font-size: 12px;
    flex-shrink: 0;
  }

  /* ---- 底部按钮 ---- */
  .wizard-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 32px;
    border-top: 1px solid var(--rule);
    background: var(--bg-elevated);
  }

  .btn {
    height: 38px;
    padding: 0 20px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 13.5px;
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

  .btn-ghost {
    background: var(--bg-surface);
  }

  .btn-primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .btn-primary:hover:not(:disabled) {
    filter: brightness(1.08);
  }

  /* ---- Toast ---- */
  .toast {
    position: fixed;
    bottom: 32px;
    left: 50%;
    transform: translateX(-50%);
    padding: 10px 18px;
    background: var(--ink);
    color: #fff;
    border-radius: var(--radius-full);
    font-size: 13px;
    z-index: 2000;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
    animation: toast-in 200ms ease;
  }

  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translate(-50%, 10px);
    }
    to {
      opacity: 1;
      transform: translate(-50%, 0);
    }
  }
</style>
