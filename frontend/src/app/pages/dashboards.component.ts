import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Dashboard } from '../core/models';
import { Notify } from '../core/ui';
import { EmptyStateComponent, PageHeaderComponent } from '../shared/ui.components';

const CATEGORY_ICONS: Record<string, string> = {
  application: 'bug_report', api: 'api', auth: 'key', web: 'language', database: 'storage', docker: 'view_in_ar',
  infrastructure: 'dns', security: 'shield', custom: 'dashboard_customize',
};

@Component({
  selector: 'lh-dashboards',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink, MatButtonModule, MatCardModule, MatFormFieldModule, MatIconModule,
    MatInputModule, MatMenuModule, PageHeaderComponent, EmptyStateComponent],
  template: `
    <lh-page-header title="Dashboards" subtitle="LogHub dashboards run on live aggregations; Grafana links open the provisioned equivalents">
      <mat-form-field class="w-200"><mat-label>Filter</mat-label><input matInput [ngModel]="filter()" (ngModelChange)="filter.set($event)" /></mat-form-field>
      @if (auth.hasRole('editor')) {
        <button mat-flat-button color="primary" (click)="create()"><mat-icon>add</mat-icon> New dashboard</button>
      }
    </lh-page-header>
    @for (folder of folders(); track folder.name) {
      <h3 class="folder-title"><mat-icon inline>folder</mat-icon> {{ folder.name }}</h3>
      <div class="card-grid">
        @for (d of folder.items; track d.id) {
          <mat-card class="dash-card">
            <a class="dash-link" [routerLink]="['/dashboards', d.id]">
              <span class="dash-icon"><mat-icon>{{ icon(d.category) }}</mat-icon></span>
              <div><div class="dash-name">{{ d.name }}</div><div class="muted small">{{ d.description }}</div>
                <div class="muted small">{{ d.widgets.length }} widgets · updated {{ d.updated_at | date: 'mediumDate' }}</div></div>
            </a>
            @if (auth.hasRole('editor')) {
              <button mat-icon-button [matMenuTriggerFor]="m" aria-label="Dashboard actions"><mat-icon>more_vert</mat-icon></button>
              <mat-menu #m="matMenu">
                <button mat-menu-item (click)="duplicate(d)"><mat-icon>content_copy</mat-icon>Duplicate</button>
                <button mat-menu-item (click)="move(d)"><mat-icon>drive_file_move</mat-icon>Move to folder</button>
                <button mat-menu-item (click)="remove(d)"><mat-icon>delete</mat-icon>Delete</button>
              </mat-menu>
            }
          </mat-card>
        }
      </div>
    } @empty { <lh-empty icon="dashboard" title="No dashboards" /> }
  `,
})
export class DashboardsComponent {
  private api = inject(ApiService);
  private router = inject(Router);
  private notify = inject(Notify);
  auth = inject(AuthService);
  dashboards = signal<Dashboard[]>([]);
  filter = signal('');
  folders = computed(() => {
    const f = this.filter().toLowerCase();
    const groups = new Map<string, Dashboard[]>();
    for (const d of this.dashboards().filter(x => !f || x.name.toLowerCase().includes(f))) {
      groups.set(d.folder || 'General', [...(groups.get(d.folder || 'General') ?? []), d]);
    }
    return [...groups.entries()].map(([name, items]) => ({ name, items }));
  });

  constructor() { this.load(); }

  load() { this.api.dashboards.list({ page_size: 200 }).subscribe(r => this.dashboards.set(r.results)); }
  icon(c: string) { return CATEGORY_ICONS[c] ?? 'dashboard'; }

  create() {
    const name = prompt('Dashboard name');
    if (!name) return;
    this.api.dashboards.create({ name, description: '', folder: 'General', category: 'custom', widgets: [], time_range: '24h', grafana_uid: '' })
      .subscribe({ next: d => this.router.navigate(['/dashboards', d.id], { queryParams: { edit: 1 } }), error: e => this.notify.error(e) });
  }
  duplicate(d: Dashboard) {
    this.api.dashboards.action<Dashboard>(d.id!, 'duplicate', { folder: 'General' })
      .subscribe({ next: () => { this.notify.ok('Duplicated'); this.load(); }, error: e => this.notify.error(e) });
  }
  move(d: Dashboard) {
    const folder = prompt('Folder', d.folder);
    if (folder === null) return;
    this.api.dashboards.update(d.id!, { folder }).subscribe({ next: () => this.load(), error: e => this.notify.error(e) });
  }
  remove(d: Dashboard) {
    if (!confirm(`Delete dashboard "${d.name}"?`)) return;
    this.api.dashboards.remove(d.id!).subscribe({ next: () => this.load(), error: e => this.notify.error(e) });
  }
}
