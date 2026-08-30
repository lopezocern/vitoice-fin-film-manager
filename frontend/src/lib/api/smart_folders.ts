import { client } from './client';

// ---- Rule tree types (serialized in rule_json) ----

export interface RuleGroup {
  type: 'group';
  logic: 'and' | 'or';
  children: RuleNode[];
}

export interface RuleCondition {
  type: 'condition';
  dimension: string;
  operator: string;
  value: unknown;
}

export type RuleNode = RuleGroup | RuleCondition;

// ---- Smart folder types ----

export interface SmartFolder {
  id: number;
  name: string;
  rule_json: RuleGroup;
  preview_count: number;
  color: string | null;
  sort_order: number;
  is_system?: boolean;
  created_at: string;
  updated_at: string;
}

export interface SmartFolderCreate {
  name: string;
  rule_json: RuleGroup;
  color?: string | null;
  sort_order?: number;
}

export interface SmartFolderUpdate {
  name?: string;
  rule_json?: RuleGroup;
  color?: string | null;
  sort_order?: number;
}

/** Lightweight media item returned by the smart-folder preview endpoint.
 *  Mirrors the backend MediaResponse fields used in the preview UI. */
export interface PreviewMedia {
  id: number;
  title: string;
  file_name: string;
  media_type: string;
  file_size: number | null;
  duration: number | null;
  width: number | null;
  height: number | null;
  thumbnail_path: string | null;
  poster_path: string | null;
  year: number | null;
  rating: number | null;
  is_favorite: boolean;
  tags: { id: number; name: string }[];
}

export const smartFoldersApi = {
  /** List all smart folders, ordered by sort_order. */
  list: async (): Promise<SmartFolder[]> =>
    client.get<SmartFolder[]>('/smart-folders'),

  /** Create a new smart folder. */
  create: async (data: SmartFolderCreate): Promise<SmartFolder> =>
    client.post<SmartFolder>('/smart-folders', data),

  /** Update a smart folder's name, rules, or appearance. */
  update: async (id: number, data: SmartFolderUpdate): Promise<SmartFolder> =>
    client.put<SmartFolder>(`/smart-folders/${id}`, data),

  /** Delete a smart folder (does not affect any media files). */
  delete: async (id: number): Promise<void> =>
    client.delete(`/smart-folders/${id}`),

  /** Preview media that matches the smart folder's rules. */
  preview: async (id: number): Promise<PreviewMedia[]> =>
    client.get<PreviewMedia[]>(`/smart-folders/${id}/preview`),
};
