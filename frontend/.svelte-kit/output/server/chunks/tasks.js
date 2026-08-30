import { c as client } from "./client2.js";
function normalizeTask(raw) {
  return {
    id: raw?.id ?? 0,
    type: raw?.type ?? "scan",
    status: raw?.status ?? "pending",
    title: raw?.title ?? raw?.subtitle ?? "",
    progress: raw?.progress ?? 0,
    total: raw?.total ?? 0,
    current: raw?.current ?? 0,
    message: raw?.subtitle ?? void 0,
    error: raw?.error_msg ?? void 0,
    result: raw?.result ?? void 0,
    library_id: raw?.library_id ?? null,
    media_id: raw?.media_id ?? null,
    started_at: raw?.started_at ?? null,
    completed_at: raw?.completed_at ?? null,
    created_at: raw?.created_at ?? "",
    updated_at: raw?.updated_at ?? ""
  };
}
const tasksApi = {
  list: async (params = {}) => (await client.get("/tasks", params, void 0, true)).map(normalizeTask),
  get: async (id) => normalizeTask(await client.get(`/tasks/${id}`)),
  cancel: (id) => client.post(`/tasks/${id}/cancel`),
  retry: (id) => client.post(`/tasks/${id}/retry`),
  clear: () => client.delete("/tasks/completed")
};
export {
  tasksApi
};
