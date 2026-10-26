import { Injectable, effect, signal } from '@angular/core';

export type ThemeMode = 'dark' | 'light';
const STORAGE_KEY = 'loghub.theme';

/** Dark by default; light is an explicit per-browser choice (never inferred from the OS). */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly mode = signal<ThemeMode>(this.read());

  constructor() {
    effect(() => {
      const mode = this.mode();
      document.documentElement.dataset['theme'] = mode;
      try { localStorage.setItem(STORAGE_KEY, mode); } catch { /* storage unavailable */ }
    });
  }

  toggle() {
    this.mode.update(m => (m === 'dark' ? 'light' : 'dark'));
  }

  private read(): ThemeMode {
    try { return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark'; } catch { return 'dark'; }
  }
}
