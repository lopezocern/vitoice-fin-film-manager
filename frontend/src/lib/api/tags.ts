import { client } from './client';

export interface Tag {
  id: string;
  name: string;
  color?: string;
  count?: number;
  tag_type_id?: number;
  parent_id?: string | null;
  description?: string | null;
  sort_order?: number;
  created_at: string;
  updated_at?: string;
  children?: Tag[];
}

export interface CreateTagInput {
  name: string;
  color?: string;
  tag_type_id?: number;
  parent_id?: number;
}

export interface UpdateTagInput {
  name?: string;
  color?: string;
  tag_type_id?: number;
  parent_id?: number;
  description?: string | null;
  sort_order?: number;
}

/** Backend wire shape of a tag (see `TagResponse` in the API). */
export type TagPayload = {
  id?: number | string | null;
  name?: string | null;
  color?: string | null;
  media_count?: number | null;
  tag_type_id?: number | null;
  parent_id?: number | string | null;
  description?: string | null;
  sort_order?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  children?: TagPayload[] | null;
};

/** Map a backend Tag (int id, media_count, children tree) → frontend Tag. */
function normalizeTag(raw: Partial<TagPayload> | null | undefined): Tag {
  return {
    id: String(raw?.id ?? ''),
    name: raw?.name ?? '',
    color: raw?.color ?? undefined,
    count: raw?.media_count ?? undefined,
    tag_type_id: raw?.tag_type_id ?? undefined,
    parent_id: raw?.parent_id != null ? String(raw.parent_id) : null,
    description: raw?.description ?? undefined,
    sort_order: raw?.sort_order ?? undefined,
    created_at: raw?.created_at ?? '',
    updated_at: raw?.updated_at ?? undefined,
    children: (raw?.children ?? []).map(normalizeTag),
  };
}

/** Flatten a tag tree into a flat array (for components that need flat lists). */
export function flattenTags(tree: Tag[]): Tag[] {
  const out: Tag[] = [];
  const walk = (nodes: Tag[]) => {
    for (const n of nodes) {
      out.push(n);
      if (n.children && n.children.length > 0) walk(n.children);
    }
  };
  walk(tree);
  return out;
}

/**
 * Keep only the sub-trees matching `typeId`.
 *
 * A node that matches keeps its whole sub-tree; a node that does not match is
 * dropped and any matching descendants are promoted to its place. Needed
 * because the tag list is a hierarchy — a flat `filter()` on the first level
 * would hide tags that sit under a differently-typed parent.
 *
 * (Moved here from the deleted `lib/manage/filters.ts` in PR6.)
 */
export function filterTreeByType(nodes: Tag[], typeId: number): Tag[] {
  const out: Tag[] = [];
  for (const n of nodes) {
    if (n.tag_type_id === typeId) {
      out.push(n);
    } else if (n.children?.length) {
      const kids = filterTreeByType(n.children, typeId);
      if (kids.length) out.push(...kids);
    }
  }
  return out;
}

export interface TagListParams {
  tag_type_id?: number;
  library_id?: string;
  exclude_av?: boolean;
  av_only?: boolean;
}

export const tagsApi = {
  // noCache=true 绕过 client 层 30s GET 缓存（受限开关切换后侧边栏需立即刷新）
  list: async (params?: TagListParams & { noCache?: boolean }): Promise<Tag[]> => {
    const query: Record<string, string> = {};
    if (params?.tag_type_id !== undefined) query.tag_type_id = String(params.tag_type_id);
    if (params?.library_id) query.library_id = params.library_id;
    if (params?.exclude_av) query.exclude_av = 'true';
    if (params?.av_only) query.av_only = 'true';
    return (
      await client.get<Partial<TagPayload>[]>('/tags', query, undefined, params?.noCache)
    ).map(normalizeTag);
  },

  get: async (id: string): Promise<Tag> =>
    normalizeTag(await client.get<Partial<TagPayload>>(`/tags/${id}`)),

  create: async (input: CreateTagInput): Promise<Tag> => {
    const payload: Record<string, unknown> = { name: input.name };
    if (input.color !== undefined) payload.color = input.color;
    if (input.tag_type_id !== undefined) payload.tag_type_id = input.tag_type_id;
    if (input.parent_id !== undefined) payload.parent_id = input.parent_id;
    return normalizeTag(await client.post<Partial<TagPayload>>('/tags', payload));
  },

  update: async (id: string, input: UpdateTagInput): Promise<Tag> =>
    normalizeTag(await client.put<Partial<TagPayload>>(`/tags/${id}`, input)),

  delete: (id: string) => client.delete<void>(`/tags/${id}`)
};
