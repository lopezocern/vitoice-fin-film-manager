import type { Task, TaskStatus } from '$lib/api/tasks';

class TasksStore {
  items = $state<Task[]>([]);
  open = $state(false);
  loading = $state(false);

  get active(): Task[] {
    return this.items.filter(
      (t) => t.status === 'pending' || t.status === 'running'
    );
  }

  get count(): number {
    return this.active.length;
  }

  get hasFailed(): boolean {
    return this.items.some((t) => t.status === 'failed');
  }

  isActive(status: TaskStatus): boolean {
    return this.items.some((t) => t.status === status);
  }

  setItems(items: Task[]): void {
    this.items = items;
  }

  upsert(task: Task): void {
    const idx = this.items.findIndex((t) => t.id === task.id);
    if (idx >= 0) {
      this.items[idx] = task;
    } else {
      this.items = [task, ...this.items];
    }
  }

  updateProgress(id: number, patch: Partial<Task>): void {
    const idx = this.items.findIndex((t) => t.id === id);
    if (idx >= 0) {
      this.items[idx] = { ...this.items[idx], ...patch };
    }
  }

  remove(id: number): void {
    this.items = this.items.filter((t) => t.id !== id);
  }

  clearCompleted(): void {
    this.items = this.items.filter(
      (t) => t.status === 'pending' || t.status === 'running'
    );
  }

  toggle(): void {
    this.open = !this.open;
  }

  /** 立即从后端拉取最新任务列表（任务发起成功后调用，徽标马上出现）。 */
  async refresh(): Promise<void> {
    const { tasksApi } = await import('$lib/api/tasks');
    try {
      const items = await tasksApi.list();
      this.setItems(items ?? []);
    } catch {
      /* 静默失败：后台轮询会兜底 */
    }
  }

  openPanel(): void {
    this.open = true;
  }

  closePanel(): void {
    this.open = false;
  }
}

export const tasks = new TasksStore();
