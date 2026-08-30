import { client, type Params } from './client';

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type TaskType = 'scan' | 'metadata' | 'thumbnail' | 'ai_tag' | 'subtitle' | 'hash' | 'scrape';

export interface Task {
  id: number;
  type: TaskType;
  status: TaskStatus;
  /** Descriptive title from backend (e.g. "扫描库 · 电影库"). */
  title: string;
  progress: number;
  total: number;
  current: number;
  /** Short status subtitle from backend (may be empty). */
  message?: string;
  error?: string;
  result?: Record<string, unknown>;
  /** Associated library / media when applicable. */
  library_id?: number | null;
  media_id?: number | null;
  /** Lifecycle timestamps (ISO strings, null when not yet set). */
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskListParams {
  status?: TaskStatus;
  type?: TaskType;
}

/** Map a backend Task (subtitle/error_msg) → frontend Task (message/error). */
function normalizeTask(raw: any): Task {
  return {
    id: raw?.id ?? 0,
    type: raw?.type ?? 'scan',
    status: raw?.status ?? 'pending',
    title: raw?.title ?? raw?.subtitle ?? '',
    progress: raw?.progress ?? 0,
    total: raw?.total ?? 0,
    current: raw?.current ?? 0,
    message: raw?.subtitle ?? undefined,
    error: raw?.error_msg ?? undefined,
    result: raw?.result ?? undefined,
    library_id: raw?.library_id ?? null,
    media_id: raw?.media_id ?? null,
    started_at: raw?.started_at ?? null,
    completed_at: raw?.completed_at ?? null,
    created_at: raw?.created_at ?? '',
    updated_at: raw?.updated_at ?? ''
  };
}

export const tasksApi = {
  list: async (params: TaskListParams = {}): Promise<Task[]> =>
    (await client.get<any[]>('/tasks', params as Params, undefined, true)).map(normalizeTask),

  get: async (id: number): Promise<Task> =>
    normalizeTask(await client.get<any>(`/tasks/${id}`)),

  cancel: (id: number) => client.post<Task>(`/tasks/${id}/cancel`),
  retry: (id: number) => client.post<Task>(`/tasks/${id}/retry`),
  clear: () => client.delete<void>('/tasks/completed')
};
