import { BreakpointObserver } from '@angular/cdk/layout';
import { DatePipe } from '@angular/common';
import { Component, DestroyRef, HostListener, ElementRef, ViewChild, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { catchError, filter, forkJoin, map, of, startWith, switchMap, timer } from 'rxjs';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Role } from '../core/models';
import { ThemeService } from '../core/theme.service';

interface NavItem { path: string; label: string; icon: string; role?: Role }

export const NAV: { group: string; items: NavItem[] }[] = [
  { group: 'Observe', items: [
    { path: '/overview', label: 'Overview', icon: 'space_dashboard' },
    { path: '/explore', label: 'Log Explorer', icon: 'manage_search' },
    { path: '/live', label: 'Live Logs', icon: 'stream' },
    { path: '/dashboards', label: 'Dashboards', icon: 'dashboard' },
    { path: '/services', label: 'Applications & Services', icon: 'apps' },
    { path: '/infrastructure', label: 'Infrastructure', icon: 'dns' },
  ]},
  { group: 'Respond', items: [
    { path: '/alerts', label: 'Alerts & Notifications', icon: 'notifications' },
    { path: '/rules', label: 'Alert Rules', icon: 'rule' },
    { path: '/detections', label: 'Detection Rules', icon: 'shield' },
    { path: '/reports', label: 'Reports', icon: 'summarize' },
  ]},
  { group: 'Manage', items: [
    { path: '/sources', label: 'Log Sources', icon: 'input' },
    { path: '/pipelines', label: 'Log Pipelines', icon: 'account_tree' },
    { path: '/retention', label: 'Retention Policies', icon: 'auto_delete' },
    { path: '/integrations', label: 'Integrations', icon: 'hub' },
    { path: '/audit', label: 'Audit Logs', icon: 'history', role: 'admin' },
    { path: '/users', label: 'Users & Roles', icon: 'group', role: 'admin' },
    { path: '/settings', label: 'System Settings', icon: 'settings' },
  ]},
];

const COLLAPSE_KEY = 'loghub.nav.collapsed';

@Component({
  selector: 'lh-shell',
  standalone: true,
  imports: [DatePipe, RouterOutlet, RouterLink, RouterLinkActive, MatSidenavModule, MatToolbarModule, MatIconModule,
    MatButtonModule, MatMenuModule, MatTooltipModule, MatDividerModule],
  template: `
    <mat-sidenav-container class="shell">
      <mat-sidenav #nav [mode]="isHandset() ? 'over' : 'side'" [opened]="!isHandset()" class="sidenav"
                   [class.collapsed]="collapsed() && !isHandset()">
        <a class="brand" routerLink="/overview">
          <span class="brand-mark"><mat-icon>insights</mat-icon></span>
          <span class="brand-text">LogHub<span class="brand-sub">{{ auth.user()?.organization?.name }}</span></span>
        </a>
        <nav aria-label="Main">
          @for (section of navSections(); track section.group) {
            <div class="nav-group">{{ section.group }}</div>
            @for (item of section.items; track item.path) {
              <a class="nav-link" [routerLink]="item.path" routerLinkActive="active-link"
                 [matTooltip]="collapsed() ? item.label : ''" matTooltipPosition="right"
                 (click)="isHandset() && nav.close()">
                <mat-icon>{{ item.icon }}</mat-icon><span class="nav-label">{{ item.label }}</span>
              </a>
            }
          }
        </nav>
      </mat-sidenav>
      <mat-sidenav-content>
        <mat-toolbar class="topbar">
          <button mat-icon-button (click)="toggleNav(nav)" aria-label="Toggle navigation"><mat-icon>menu</mat-icon></button>
          <div class="crumbs"><span>{{ crumb().group }}</span><mat-icon inline>chevron_right</mat-icon><strong>{{ crumb().label }}</strong></div>
          <label class="global-search">
            <mat-icon inline>search</mat-icon>
            <input #search type="search" placeholder="Search logs…" aria-label="Search logs"
                   (keydown.enter)="runSearch(search.value); search.value = ''; search.blur()" />
            <kbd>/</kbd>
          </label>
          <span class="spacer"></span>
          <a class="health-pill" routerLink="/integrations" [matTooltip]="healthDetail()">
            <span class="dot {{ health().status }}"></span><span class="health-label">{{ healthLabel() }}</span>
          </a>
          <button mat-icon-button (click)="theme.toggle()" [matTooltip]="theme.mode() === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
                  [attr.aria-label]="theme.mode() === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'">
            <mat-icon>{{ theme.mode() === 'dark' ? 'light_mode' : 'dark_mode' }}</mat-icon>
          </button>
          <a mat-icon-button class="topbar-icon" routerLink="/alerts" [attr.aria-label]="firing() + ' firing alerts'" matTooltip="Firing alerts">
            <mat-icon>notifications</mat-icon>
            @if (firing() > 0) { <span class="badge-count">{{ firing() > 99 ? '99+' : firing() }}</span> }
          </a>
          <span class="clock" matTooltip="Server time is UTC">{{ now() | date: 'HH:mm:ss' : 'UTC' }} UTC</span>
          <button mat-button class="user-chip" [matMenuTriggerFor]="userMenu" aria-label="Account menu">
            <span class="avatar">{{ initials() }}</span>
          </button>
          <mat-menu #userMenu="matMenu" xPosition="before">
            <div class="menu-empty"><strong>{{ auth.user()?.username }}</strong><br />
              <span class="role-pill">{{ auth.user()?.role }}</span> · {{ auth.user()?.organization?.name }}</div>
            <mat-divider />
            <a mat-menu-item routerLink="/settings"><mat-icon>settings</mat-icon>Settings</a>
            <a mat-menu-item href="/api/docs/" target="_blank" rel="noopener"><mat-icon>api</mat-icon>API docs</a>
            <button mat-menu-item (click)="auth.logout()"><mat-icon>logout</mat-icon>Sign out</button>
          </mat-menu>
        </mat-toolbar>
        <main class="content"><router-outlet /></main>
      </mat-sidenav-content>
    </mat-sidenav-container>
  `,
})
export class ShellComponent {
  @ViewChild('search') searchInput?: ElementRef<HTMLInputElement>;
  auth = inject(AuthService);
  theme = inject(ThemeService);
  private api = inject(ApiService);
  private router = inject(Router);
  private bp = inject(BreakpointObserver);
  isHandset = toSignal(this.bp.observe('(max-width: 960px)').pipe(map(r => r.matches)), { initialValue: false });
  navSections = computed(() => NAV.map(s => ({ ...s, items: s.items.filter(i => !i.role || this.auth.hasRole(i.role)) })));
  collapsed = signal(this.readCollapsed());
  now = toSignal(timer(0, 1000).pipe(map(() => new Date())), { initialValue: new Date() });
  health = signal<{ status: string; services: { name: string; status: string }[] }>({ status: 'unknown', services: [] });
  firing = signal(0);

  private url = toSignal(this.router.events.pipe(
    filter(e => e instanceof NavigationEnd), map(() => this.router.url), startWith(this.router.url)), { initialValue: '' });
  crumb = computed(() => {
    const path = '/' + (this.url().split(/[?#]/)[0].split('/')[1] ?? '');
    for (const s of NAV) {
      const item = s.items.find(i => i.path === path);
      if (item) return { group: s.group, label: item.label };
    }
    return { group: 'LogHub', label: '' };
  });
  initials = computed(() => {
    const u = this.auth.user();
    const name = [u?.first_name, u?.last_name].filter(Boolean).join(' ') || u?.username || '?';
    return name.split(/\s+/).map(p => p[0]).join('').slice(0, 2);
  });
  healthLabel = computed(() => {
    const bad = this.health().services.filter(s => s.status === 'unhealthy' || s.status === 'degraded');
    if (this.health().status === 'unknown') return 'Checking…';
    return bad.length ? (bad.length === 1 ? `${bad[0].name} needs attention` : `${bad.length} services need attention`) : 'All systems operational';
  });
  healthDetail = computed(() => this.health().services.map(s => `${s.name}: ${s.status}`).join(' · '));

  constructor() {
    timer(0, 60000).pipe(
      switchMap(() => forkJoin({
        health: this.api.platformHealth().pipe(catchError(() => of({ status: 'unhealthy', services: [] }))),
        firing: this.api.events.list({ status: 'firing', page_size: 1 }).pipe(map(r => r.count), catchError(() => of(0))),
      })),
      takeUntilDestroyed(inject(DestroyRef)),
    ).subscribe(({ health, firing }) => {
      this.health.set({ status: health.status, services: health.services.filter((s: any) => s.enabled !== false) });
      this.firing.set(firing);
    });
  }

  @HostListener('document:keydown', ['$event'])
  focusSearch(e: KeyboardEvent) {
    const target = e.target as HTMLElement;
    if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(target.tagName) && !target.isContentEditable) {
      e.preventDefault();
      this.searchInput?.nativeElement.focus();
    }
  }

  runSearch(q: string) {
    if (q.trim()) this.router.navigate(['/explore'], { queryParams: { q: q.trim(), range: '24h' } });
  }

  toggleNav(nav: { toggle: () => void }) {
    if (this.isHandset()) return nav.toggle();
    this.collapsed.update(c => !c);
    try { localStorage.setItem(COLLAPSE_KEY, this.collapsed() ? '1' : '0'); } catch { /* storage unavailable */ }
  }

  private readCollapsed(): boolean {
    try { return localStorage.getItem(COLLAPSE_KEY) === '1'; } catch { return false; }
  }
}
