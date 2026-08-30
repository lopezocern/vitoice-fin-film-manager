import type { Media } from '$lib/api/media';

export interface MediaMark {
  id: string;
  start: number;
  end?: number;
  label?: string;
}

class PlayerStore {
  current = $state<Media | null>(null);
  playing = $state(false);
  currentTime = $state(0);
  duration = $state(0);
  volume = $state(1);
  muted = $state(false);
  playbackRate = $state(1);
  fullscreen = $state(false);
  loop = $state(false);
  captions = $state(false);

  marks = $state<MediaMark[]>([]);
  currentMarkStart = $state<number | null>(null);

  get progress(): number {
    return this.duration > 0 ? (this.currentTime / this.duration) * 100 : 0;
  }

  get remaining(): number {
    return Math.max(0, this.duration - this.currentTime);
  }

  load(media: Media): void {
    this.current = media;
    this.currentTime = 0;
    this.playing = false;
    this.marks = [];
    this.currentMarkStart = null;
  }

  clear(): void {
    this.current = null;
    this.playing = false;
    this.currentTime = 0;
    this.duration = 0;
    this.marks = [];
    this.currentMarkStart = null;
  }

  play(): void {
    this.playing = true;
  }

  pause(): void {
    this.playing = false;
  }

  togglePlay(): void {
    this.playing = !this.playing;
  }

  seek(time: number): void {
    this.currentTime = Math.max(0, Math.min(time, this.duration));
  }

  step(seconds: number): void {
    this.seek(this.currentTime + seconds);
  }

  stepFrame(forward: boolean): void {
    const frameTime = 1 / 30;
    this.step(forward ? frameTime : -frameTime);
  }

  setVolume(v: number): void {
    this.volume = Math.max(0, Math.min(1, v));
    if (v > 0) this.muted = false;
  }

  toggleMute(): void {
    this.muted = !this.muted;
  }

  setPlaybackRate(rate: number): void {
    this.playbackRate = Math.max(0.25, Math.min(4, rate));
  }

  toggleFullscreen(): void {
    this.fullscreen = !this.fullscreen;
  }

  toggleLoop(): void {
    this.loop = !this.loop;
  }

  toggleCaptions(): void {
    this.captions = !this.captions;
  }

  markIn(): void {
    this.currentMarkStart = this.currentTime;
  }

  markOut(): void {
    if (this.currentMarkStart !== null) {
      const start = this.currentMarkStart;
      const end = this.currentTime;
      if (end > start) {
        this.marks = [
          ...this.marks,
          {
            id: crypto.randomUUID(),
            start,
            end
          }
        ];
      }
      this.currentMarkStart = null;
    }
  }

  removeMark(id: string): void {
    this.marks = this.marks.filter((m) => m.id !== id);
  }

  clearMarks(): void {
    this.marks = [];
    this.currentMarkStart = null;
  }
}

export const player = new PlayerStore();
