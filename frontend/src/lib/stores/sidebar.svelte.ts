class SidebarStore {
  collapsed = $state(false);
  width = $state(260);

  get expanded(): boolean {
    return !this.collapsed;
  }

  toggle(): void {
    this.collapsed = !this.collapsed;
  }

  set(collapsed: boolean): void {
    this.collapsed = collapsed;
  }

  expand(): void {
    this.collapsed = false;
  }

  collapse(): void {
    this.collapsed = true;
  }
}

export const sidebar = new SidebarStore();
