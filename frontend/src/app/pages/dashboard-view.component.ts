import { Component, OnInit, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Dashboard, Widget } from '../core/models';
import { LEVELS, Notify, TIME_RANGES } from '../core/ui';
import { EmptyStateComponent, PageHeaderComponent } from '../shared/ui.components';
import { WidgetComponent } from '../shared/widget.component';

function blankWidget(): Widget {
  return { id: Math.random().toString(36).slice(2, 8), title: 'New widget', type: 'timeseries', source: 'logs',
           query: {}, agg: { type: 'histogram', split_by: 'level' }, layout: { cols: 2 } };
}

@Component({
  selector: 'lh-dashboard-view',
  standalone: true,
  imports: [FormsModule, RouterLink, MatButtonModule, MatCardModule, MatFormFieldModule, MatIconModule, MatInputModule,
    MatSelectModule, PageHeaderComponent, WidgetComponent, EmptyStateComponent],
  template: `
    @if (dash(); as d) {
      <lh-page-header [title]="d.name" [subtitle]="d.description">
        <mat-select class="range-select" [(ngModel)]="range" aria-label="Time range">
          @for (r of ranges; track r.value) { <mat-option [value]="r.value">{{ r.label }}</mat-option> }
        </mat-select>
        <button mat-icon-button (click)="tick.set(tick() + 1)" aria-label="Refresh"><mat-icon>refresh</mat-icon></button>
        @if (d.grafana_uid && grafanaUrl()) {
          <a mat-stroked-button [href]="grafanaUrl() + '/d/' + d.grafana_uid" target="_blank" rel="noopener"><mat-icon>open_in_new</mat-icon> Grafana</a>
        }
        @if (auth.hasRole('editor')) {
          @if (editing()) {
            <button mat-stroked-button (click)="addWidget()"><mat-icon>add</mat-icon> Widget</button>
            <button mat-flat-button color="primary" (click)="save()"><mat-icon>save</mat-icon> Save</button>
          } @else {
            <button mat-stroked-button (click)="editing.set(true)"><mat-icon>edit</mat-icon> Edit</button>
          }
        }
      </lh-page-header>

      @if (editing()) {
        <mat-card class="query-card">
          <div class="filter-row">
            <mat-form-field class="grow"><mat-label>Name</mat-label><input matInput [(ngModel)]="d.name" /></mat-form-field>
            <mat-form-field class="w-200"><mat-label>Folder</mat-label><input matInput [(ngModel)]="d.folder" /></mat-form-field>
            <mat-form-field class="grow"><mat-label>Description</mat-label><input matInput [(ngModel)]="d.description" /></mat-form-field>
          </div>
        </mat-card>
      }

      <div class="widget-grid">
        @for (w of d.widgets; track w.id; let i = $index) {
          <div class="widget-cell" [style.grid-column]="'span ' + w.layout.cols">
            @if (editing()) {
              <mat-card class="widget-editor">
                <div class="filter-row">
                  <mat-form-field class="grow"><mat-label>Title</mat-label><input matInput [(ngModel)]="w.title" /></mat-form-field>
                  <mat-form-field class="w-140"><mat-label>Type</mat-label>
                    <mat-select [(ngModel)]="w.type" (selectionChange)="typeChanged(w)">
                      @for (t of types; track t) { <mat-option [value]="t">{{ t }}</mat-option> }
                    </mat-select></mat-form-field>
                  <mat-form-field class="w-120"><mat-label>Width</mat-label>
                    <mat-select [(ngModel)]="w.layout.cols">@for (c of [1, 2, 3, 4]; track c) { <mat-option [value]="c">{{ c }}/4</mat-option> }</mat-select></mat-form-field>
                </div>
                <div class="filter-row">
                  <mat-form-field class="w-140"><mat-label>Data</mat-label>
                    <mat-select [(ngModel)]="w.source"><mat-option value="logs">Logs</mat-option><mat-option value="prometheus">Prometheus</mat-option></mat-select></mat-form-field>
                  @if (w.source === 'prometheus') {
                    <mat-form-field class="grow"><mat-label>PromQL</mat-label><input matInput class="mono" [(ngModel)]="w.promql" /></mat-form-field>
                  } @else {
                    <mat-form-field class="grow"><mat-label>Query</mat-label><input matInput [(ngModel)]="w.query.q" /></mat-form-field>
                    <mat-form-field class="w-160"><mat-label>Levels</mat-label>
                      <mat-select multiple [(ngModel)]="w.query.level">@for (l of levels; track l) { <mat-option [value]="l">{{ l }}</mat-option> }</mat-select></mat-form-field>
                    @if (w.type !== 'logs' && w.agg) {
                      @if (w.agg.type === 'terms') {
                        <mat-form-field class="w-160"><mat-label>Group by field</mat-label><input matInput [(ngModel)]="w.agg.field" /></mat-form-field>
                      }
                      @if (w.agg.type === 'histogram') {
                        <mat-form-field class="w-160"><mat-label>Split by field</mat-label><input matInput [(ngModel)]="w.agg.split_by" /></mat-form-field>
                      }
                    }
                  }
                </div>
                <div class="editor-actions">
                  <button mat-button (click)="move(i, -1)" [disabled]="i === 0"><mat-icon>arrow_back</mat-icon></button>
                  <button mat-button (click)="move(i, 1)" [disabled]="i === d.widgets.length - 1"><mat-icon>arrow_forward</mat-icon></button>
                  <button mat-button color="warn" (click)="removeWidget(i)"><mat-icon>delete</mat-icon> Remove</button>
                </div>
              </mat-card>
            } @else {
              <lh-widget [widget]="w" [range]="range" [refresh]="tick()" />
            }
          </div>
        } @empty {
          <lh-empty icon="widgets" title="This dashboard has no widgets">Use Edit → Widget to add one.</lh-empty>
        }
      </div>
    }
  `,
})
export class DashboardViewComponent implements OnInit {
  id = input.required<string>();
  private api = inject(ApiService);
  private notify = inject(Notify);
  private route = inject(ActivatedRoute);
  auth = inject(AuthService);
  dash = signal<Dashboard | null>(null);
  editing = signal(false);
  tick = signal(0);
  range = '24h';
  ranges = TIME_RANGES;
  levels = LEVELS;
  types = ['stat', 'timeseries', 'bar', 'pie', 'table', 'logs'];
  grafanaUrl = signal('');

  ngOnInit() {
    this.api.dashboards.get(Number(this.id())).subscribe(d => {
      this.dash.set(structuredClone(d));
      this.range = d.time_range || '24h';
    });
    this.editing.set(this.route.snapshot.queryParamMap.has('edit'));
    this.api.integrations().subscribe(list => this.grafanaUrl.set(list.find(i => i.provider === 'grafana')?.public_url ?? ''));
  }

  typeChanged(w: Widget) {
    w.agg = w.type === 'timeseries' ? { type: 'histogram', split_by: 'level' }
      : w.type === 'stat' ? { type: 'metric' }
      : w.type === 'logs' ? undefined
      : { type: 'terms', field: w.agg?.field || 'service', size: 10 };
  }
  addWidget() { this.dash.update(d => d && { ...d, widgets: [...d.widgets, blankWidget()] }); }
  removeWidget(i: number) { this.dash.update(d => d && { ...d, widgets: d.widgets.filter((_, idx) => idx !== i) }); }
  move(i: number, delta: number) {
    this.dash.update(d => {
      if (!d) return d;
      const w = [...d.widgets];
      [w[i], w[i + delta]] = [w[i + delta], w[i]];
      return { ...d, widgets: w };
    });
  }
  save() {
    const d = this.dash()!;
    this.api.dashboards.update(d.id!, { name: d.name, folder: d.folder, description: d.description, widgets: d.widgets, time_range: this.range })
      .subscribe({
        next: saved => { this.dash.set(structuredClone(saved)); this.editing.set(false); this.notify.ok('Dashboard saved'); },
        error: e => this.notify.error(e),
      });
  }
}
