import { client, type Params } from './client';

export type ScrapeMode = 'none' | 'movie' | 'tv' | 'av' | 'custom';

export interface Library {
  id: string;
  name: string;
  path: string;
  root_path?: string;
  description?: string;
  scrape_mode?: ScrapeMode;
  is_restricted?: boolean;
  media_count?: number;
  created_at: string;
  updated_at: string;
}

export interface CreateLibraryInput {
  name: string;
  path: string;
  description?: string;
}

export interface UpdateLibraryInput {
  name?: string;
  path?: string;
  description?: string;
}

/** 删除资源库时被清理的空标签 */
export interface CleanedTag {
  id: string | number;
  name: string;
}

/** DELETE /api/libraries/{id} 的响应体 */
export interface DeleteLibraryResult {
  /** 被清理的空标签列表（仅 clean_empty_tags=true 时返回） */
  cleaned_tags?: CleanedTag[];
  /** 被清理的空标签数量 */
  cleaned_tags_count?: number;
}

/**
 * Backend wire shape of a library (see `LibraryResponse` in the API).
 *
 * Every field is optional on purpose: `normalizeLibrary` is defensive and
 * substitutes defaults, and the backend omits nullable fields. Typing the
 * payload instead of using `any` means a backend rename shows up here as a
 * compile error rather than silently producing an empty string at runtime.
 */
export interface LibraryPayload {
  id: number | string;
  name: string;
  root_path: string;
  description?: string | null;
  scrape_mode?: ScrapeMode | null;
  is_restricted?: boolean | null;
  media_count?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** Map a backend Library (root_path / int id) → frontend Library (path / string id). */
function normalizeLibrary(raw: Partial<LibraryPayload> | null | undefined): Library {
  return {
    id: String(raw?.id ?? ''),
    name: raw?.name ?? '',
    path: raw?.root_path ?? '',
    root_path: raw?.root_path ?? '',
    description: raw?.description ?? undefined,
    scrape_mode: raw?.scrape_mode ?? undefined,
    is_restricted: raw?.is_restricted ?? false,
    media_count: raw?.media_count ?? 0,
    created_at: raw?.created_at ?? '',
    updated_at: raw?.updated_at ?? ''
  };
}

/**
 * Map a backend TreeNode (node_type is a plain string) → frontend TreeNode
 * (`node_type` narrowed to the union the UI switches on).
 */
function normalizeTreeNode(raw: Partial<TreeNodePayload> | null | undefined): TreeNode {
  return {
    name: raw?.name ?? '',
    rel_path: raw?.rel_path ?? '',
    node_type: raw?.node_type === 'directory' ? 'directory' : 'file',
    size: raw?.size ?? undefined,
    modified_at: raw?.modified_at ?? undefined,
    media_id: raw?.media_id ?? undefined,
    is_scraped: !!raw?.is_scraped,
    has_poster: !!raw?.has_poster,
    child_count: raw?.child_count ?? undefined,
  };
}

export const librariesApi = {
  // noCache=true 时绕过 client 层 30s GET 缓存——侧边栏 reload/受限开关切换
  // 等场景必须拿到最新数据（否则保存 show_restricted 后 30s 内仍显示旧库列表）。
  list: async (noCache = false): Promise<Library[]> =>
    (
      await client.get<Partial<LibraryPayload>[]>(
        '/libraries',
        undefined,
        undefined,
        noCache
      )
    ).map(normalizeLibrary),

  get: async (id: string): Promise<Library> =>
    normalizeLibrary(await client.get<Partial<LibraryPayload>>(`/libraries/${id}`)),

  create: async (input: CreateLibraryInput): Promise<Library> => {
    const payload: Record<string, unknown> = {
      name: input.name,
      root_path: input.path
    };
    if (input.description !== undefined) payload.description = input.description;
    return normalizeLibrary(
      await client.post<Partial<LibraryPayload>>('/libraries', payload)
    );
  },

  update: async (id: string, input: UpdateLibraryInput): Promise<Library> => {
    const payload: Record<string, unknown> = {};
    if (input.name !== undefined) payload.name = input.name;
    if (input.path !== undefined) payload.root_path = input.path;
    if (input.description !== undefined) payload.description = input.description;
    return normalizeLibrary(
      await client.put<Partial<LibraryPayload>>(`/libraries/${id}`, payload)
    );
  },

  delete: (id: string, cleanEmptyTags = false): Promise<DeleteLibraryResult> =>
    client.delete<DeleteLibraryResult>(
      `/libraries/${id}`,
      cleanEmptyTags ? { clean_empty_tags: true } : undefined
    ),
  scan: (id: string) => client.post<{ task_id: string }>(`/libraries/${id}/scan`),
  rescan: (id: string) => client.post<{ task_id: string }>(`/libraries/${id}/rescan`),

  /** Import external files into a library directory (server-side copy/move + scan). */
  importFiles: async (id: string, targetDir: string, sourcePaths: string[], action: 'copy' | 'move' = 'copy') => {
    const res = await client.post<ImportFilesResult>(`/libraries/${id}/files/import`, {
      source_paths: sourcePaths,
      target_dir: targetDir,
      action,
    });
    return {
      imported: res?.imported ?? 0,
      skipped: res?.skipped ?? 0,
      results: res?.results ?? [],
    };
  },

  /** Get the file system directory tree for a library (lazy-loaded). */
  tree: async (id: string, path = ''): Promise<TreeNode[]> => {
    const params: Params = {};
    if (path) params.path = path;
    const res = await client.get<TreeResponse>(`/libraries/${id}/tree`, params);
    return (res?.nodes ?? []).map(normalizeTreeNode);
  },

  /** Create a new directory within a library. */
  createDirectory: async (id: string, parentPath: string, dirName: string) =>
    client.post<CreateDirectoryResult>(`/libraries/${id}/directories`, {
      parent_path: parentPath,
      dir_name: dirName,
    }),

  /** Rename a directory on disk (updates all affected media paths). */
  renameDirectory: async (id: string, oldRelPath: string, newName: string) =>
    client.put<RenameDirectoryResult>(`/libraries/${id}/directories/rename`, {
      old_rel_path: oldRelPath,
      new_name: newName,
    }),

  /** Delete a directory on disk. */
  deleteDirectory: async (id: string, relPath: string, recursive = false) => {
    const params: Params = { rel_path: relPath };
    if (recursive) params.recursive = true;
    return client.delete<DeleteDirectoryResult>(`/libraries/${id}/directories`, params);
  },

  /** Move files to a target directory within a library. */
  moveFiles: async (
    sourceLibraryId: string,
    mediaIds: string[],
    targetLibraryId: string,
    targetDir = ''
  ) =>
    client.put<MoveFilesResult>(
      `/libraries/${sourceLibraryId}/files/move`,
      { target_library_id: parseInt(targetLibraryId), target_dir: targetDir },
      { media_ids: mediaIds.join(',') }
    ),
};

// ---- Directory tree types ----

/** Wire shape of a tree node (`node_type` is an unconstrained string server-side). */
export interface TreeNodePayload {
  name: string;
  rel_path: string;
  node_type: string;
  size?: number | null;
  modified_at?: number | null;
  media_id?: number | null;
  is_scraped?: boolean | null;
  has_poster?: boolean | null;
  child_count?: number | null;
}

export interface TreeNode {
  name: string;
  rel_path: string;
  node_type: 'directory' | 'file';
  size?: number;
  modified_at?: number;
  media_id?: number;
  is_scraped: boolean;
  has_poster: boolean;
  child_count?: number;
}

/** GET /api/libraries/{id}/tree — see `TreeResponse` in the API. */
export interface TreeResponse {
  library_id: number;
  library_name: string;
  rel_path: string;
  nodes: TreeNodePayload[];
}

/** Per-file outcome of POST /api/libraries/{id}/files/import. */
export interface ImportFileOutcome {
  source: string;
  status: string;
  reason?: string;
  imported_as?: string;
  renamed?: boolean;
}

export interface ImportFilesResult {
  status: string;
  imported: number;
  skipped: number;
  results: ImportFileOutcome[];
  scan?: Record<string, unknown>;
}

export interface CreateDirectoryResult {
  status: string;
  library_id: number;
  rel_path: string;
  name: string;
}

export interface RenameDirectoryResult {
  status: string;
  library_id: number;
  old_rel_path: string;
  new_rel_path: string;
  updated_media_count: number;
}

export interface DeleteDirectoryResult {
  status: string;
  library_id: number;
  rel_path: string;
  affected_media_count: number;
}

export interface MoveFileError {
  media_id: number;
  reason: string;
}

export interface MoveFilesResult {
  status: string;
  moved: number;
  skipped: number;
  errors: MoveFileError[];
}
