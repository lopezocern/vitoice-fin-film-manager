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

/** Backend wire shape of a task (see the /api/tasks responses). */
export type TaskPayload = {
  id?: number | null;
  type?: TaskType | null;
  status?: TaskStatus | null;
  title?: string | null;
  subtitle?: string | null;
  progress?: number | null;
  total?: number | null;
  current?: number | null;
  error_msg?: string | null;
  result?: Record<string, unknown> | null;
  library_id?: number | null;
  media_id?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

/** Map a backend Task (subtitle/error_msg) → frontend Task (message/error). */
function normalizeTask(raw: Partial<TaskPayload> | null | undefined): Task {
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
    (await client.get<Partial<TaskPayload>[]>('/tasks', params as Params, undefined, true)).map(
      normalizeTask
    ),

  get: async (id: number): Promise<Task> =>
    normalizeTask(await client.get<Partial<TaskPayload>>(`/tasks/${id}`)),

  // These return a raw task row, so normalize before handing it back — the
  // previous `Task` annotation claimed `message`/`error` fields the backend
  // actually sends as `subtitle`/`error_msg`.
  cancel: async (id: number): Promise<Task> =>
    normalizeTask(await client.post<Partial<TaskPayload>>(`/tasks/${id}/cancel`)),
  retry: async (id: number): Promise<Task> =>
    normalizeTask(await client.post<Partial<TaskPayload>>(`/tasks/${id}/retry`)),
  clear: () => client.delete<void>('/tasks/completed')
};
