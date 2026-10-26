import { DatePipe } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { Subject, switchMap, timer } from 'rxjs';
import { ApiService } from '../core/api.service';
import { Notify, TIME_RANGES, formatBytes, formatNumber } from '../core/ui';
import { barOption, donutOption, timeSeriesOption } from '../shared/charts';
import {
  ChartComponent, EmptyStateComponent, LevelBadgeComponent, PageHeaderComponent, StatTileComponent, StatusChipComponent,
} from '../shared/ui.components';

@Component({
  selector: 'lh-overview',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink, MatCardModule, MatSelectModule, MatIconModule, MatButtonModule,
    MatProgressBarModule, PageHeaderComponent, StatTileComponent, ChartComponent, EmptyStateComponent, StatusChipComponent,
    LevelBadgeComponent],
  template: `
    <lh-page-header title="Overview" subtitle="Ingestion, severity and platform health across your organization">
      @if (d()?.generated_at) { <span class="muted small">Updated {{ d().generated_at | date: 'HH:mm:ss' }} · auto-refresh 30 s</span> }
      <mat-select class="range-select" [(ngModel)]="range" (selectionChange)="reload$.next()" aria-label="Time range">
        @for (r of ranges; track r.value) { <mat-option [value]="r.value">{{ r.label }}</mat-option> }
      </mat-select>
    </lh-page-header>
    @if (loading() && !d()) { <mat-progress-bar mode="indeterminate" /> }

    @if (d(); as d) {
      @if (!d.elasticsearch_available) {
        <div class="banner error"><mat-icon>error</mat-icon>Elasticsearch is unavailable: {{ d.elasticsearch_error }}. Log metrics are hidden rather than estimated.</div>
      }
      <div class="section-label">Traffic &amp; severity</div>
      <section class="kpi-grid">
        <lh-stat label="Events" icon="data_usage" [value]="num(d.total_events)" [hint]="'last ' + range" />
        <lh-stat label="Events / sec" icon="speed" [value]="num(d.events_per_second)" hint="last 60 seconds" />
        <lh-stat label="Errors" icon="error" [value]="num(d.errors)" [tone]="d.errors ? 'warn' : 'normal'" [hint]="pct(d.errors, d.total_events) + ' of events'" />
        <lh-stat label="Warnings" icon="warning" [value]="num(d.warnings)" [hint]="pct(d.warnings, d.total_events) + ' of events'" />
        <lh-stat label="Critical" icon="report" [value]="num(d.critical)" [tone]="d.critical ? 'alert' : 'normal'" hint="highest severity" />
        <lh-stat label="Open alerts" icon="notifications_active" [value]="d.open_alerts" [tone]="d.open_alerts ? 'alert' : 'normal'" hint="firing or acknowledged" />
      </section>
      <div class="section-label">Pipeline health</div>
      <section class="kpi-grid cols-4">
        <lh-stat label="Active sources" icon="input" [value]="d.sources.active + ' / ' + d.sources.total"
                 [hint]="d.sources.stale + ' stale · ' + d.sources.pending + ' pending'" [tone]="d.sources.stale ? 'warn' : 'normal'" />
        <lh-stat label="Unhealthy collectors" icon="lan" [value]="d.collectors.unhealthy"
                 [tone]="d.collectors.unhealthy ? 'warn' : 'normal'" [hint]="'of ' + d.collectors.total + ' collectors'" />
        <lh-stat label="Events lost" icon="sync_problem" [value]="num(d.ingestion_failures)"
                 [tone]="d.ingestion_failures ? 'alert' : 'normal'" hint="DLQ overflow / expiry" />
        <lh-stat label="Storage" icon="storage" [value]="bytes(d.storage?.data_stream?.store_size_bytes)"
                 [hint]="d.storage?.disk ? 'cluster disk ' + d.storage.disk.used_percent + '% used' : ''"
                 [tone]="(d.storage?.disk?.used_percent ?? 0) > 85 ? 'alert' : 'normal'" />
      </section>

      @if (d.elasticsearch_available && !d.total_events) {
        <mat-card><lh-empty icon="inbox" title="No log events in this time range">
          Register a <a routerLink="/sources">log source</a> and send your first event, or start the demo generator
          (<code>docker compose --profile demo up -d demo-generator</code>).
        </lh-empty></mat-card>
      } @else if (d.elasticsearch_available) {
        <div class="section-label">Activity</div>
        <section class="grid-3">
          <mat-card><mat-card-header><mat-card-title>Log volume</mat-card-title>
            <mat-card-subtitle>events by severity · {{ d.volume.interval }} buckets</mat-card-subtitle></mat-card-header>
            <mat-card-content><lh-chart [options]="charts().volume" [height]="260" /></mat-card-content></mat-card>
          <mat-card><mat-card-header><mat-card-title>Severity mix</mat-card-title><mat-card-subtitle>events per level</mat-card-subtitle></mat-card-header>
            <mat-card-content><lh-chart [options]="charts().levels" [height]="260" /></mat-card-content></mat-card>
        </section>
        <section class="grid-2">
          <mat-card><mat-card-header><mat-card-title>Top error-producing applications</mat-card-title><mat-card-subtitle>error + critical events</mat-card-subtitle></mat-card-header>
            <mat-card-content>
              @if (d.top_error_services.length) { <lh-chart [options]="charts().topErrors" [height]="250" /> }
              @else { <lh-empty icon="check_circle" title="No errors in range" /> }
            </mat-card-content></mat-card>
          <mat-card><mat-card-header><mat-card-title>Logs by environment</mat-card-title><mat-card-subtitle>share of events</mat-card-subtitle></mat-card-header>
            <mat-card-content><lh-chart [options]="charts().envs" [height]="250" /></mat-card-content></mat-card>
          <mat-card><mat-card-header><mat-card-title>Error rate by application</mat-card-title></mat-card-header>
            <mat-card-content class="table-scroll">
              <table class="data-table">
                <thead><tr><th>Service</th><th class="num">Errors</th><th class="num">Events</th><th>Error rate</th></tr></thead>
                <tbody>
                  @for (r of d.error_rate_by_service; track r.service) {
                    <tr><td><a [routerLink]="['/explore']" [queryParams]="{ service: r.service, level: 'error,critical', range }">{{ r.service }}</a></td>
                      <td class="num">{{ num(r.errors) }}</td><td class="num">{{ num(r.events) }}</td>
                      <td><div class="meter"><div class="meter-fill" [style.width.%]="r.error_rate ?? 0" [class.hot]="(r.error_rate ?? 0) >= 5"></div></div>
                        <span class="small tabular">{{ r.error_rate === null ? '—' : r.error_rate + '%' }}</span></td></tr>
                  } @empty { <tr><td colspan="4" class="muted">No errors in range.</td></tr> }
                </tbody>
              </table>
            </mat-card-content></mat-card>
          <mat-card><mat-card-header><mat-card-title>Most frequent error messages</mat-card-title></mat-card-header>
            <mat-card-content class="table-scroll">
              <table class="data-table">
                <thead><tr><th>Message</th><th class="num">Count</th></tr></thead>
                <tbody>
                  @for (m of d.frequent_errors; track m.key) {
                    <tr><td class="mono wrap"><a [routerLink]="['/explore']" [queryParams]="{ q: '&quot;' + m.key + '&quot;', range }">{{ m.key }}</a></td><td class="num">{{ num(m.count) }}</td></tr>
                  } @empty { <tr><td colspan="2" class="muted">No errors in range.</td></tr> }
                </tbody>
              </table>
            </mat-card-content></mat-card>
        </section>
      }

      <div class="section-label">Operations</div>
      <section class="grid-2">
        <mat-card><mat-card-header><mat-card-title>Recent alerts</mat-card-title>
            <mat-card-subtitle>{{ d.open_alerts }} open · <a routerLink="/alerts">view all</a></mat-card-subtitle></mat-card-header>
          <mat-card-content>
            <table class="data-table">
              <tbody>
                @for (a of d.recent_alerts; track a.id) {
                  <tr><td><lh-level [level]="a.severity" /></td>
                    <td><a [routerLink]="['/alerts/events', a.id]">{{ a.title }}</a></td>
                    <td><lh-status [status]="a.status" /></td><td class="muted nowrap">{{ a.started_at | date: 'MMM d, HH:mm' }}</td></tr>
                } @empty { <tr><td class="muted">No alerts have fired.</td></tr> }
              </tbody>
            </table>
          </mat-card-content></mat-card>
        <mat-card><mat-card-header><mat-card-title>Service &amp; infrastructure health</mat-card-title>
            <mat-card-subtitle>checked every 60 s · <a routerLink="/integrations">integrations</a></mat-card-subtitle></mat-card-header>
          <mat-card-content>
            <table class="data-table">
              <tbody>
                @for (s of d.services_health; track s.provider) {
                  <tr><td>{{ s.name }}</td><td><lh-status [status]="s.status" /></td><td class="muted small wrap">{{ s.message }}</td></tr>
                }
                @for (c of d.collectors.items; track c.name) {
                  <tr><td>{{ c.name }}</td><td><lh-status [status]="c.status" /></td><td class="muted small wrap">{{ c.message }}</td></tr>
                }
              </tbody>
            </table>
          </mat-card-content></mat-card>
      </section>
    }
  `,
})
export class OverviewComponent {
  private api = inject(ApiService);
  private notify = inject(Notify);
  ranges = TIME_RANGES;
  range = '24h';
  d = signal<any>(null);
  loading = signal(true);
  reload$ = new Subject<void>();
  num = formatNumber;
  bytes = formatBytes;

  // Chart options are rebuilt only when data changes (not on every change detection).
  charts = computed(() => {
    const d = this.d();
    if (!d?.volume) return { volume: {}, levels: {}, envs: {}, topErrors: {} };
    return {
      volume: timeSeriesOption(d.volume),
      levels: barOption(d.by_level, { colorByKey: true }),
      envs: donutOption(d.by_environment),
      topErrors: barOption(d.top_error_services),
    };
  });

  constructor() {
    const destroyRef = inject(DestroyRef);
    // Refresh every 30s; restart the timer when the range changes.
    this.reload$.pipe(
      switchMap(() => timer(0, 30000)),
      switchMap(() => { this.loading.set(true); return this.api.overview(this.range); }),
      takeUntilDestroyed(destroyRef),
    ).subscribe({
      next: d => { this.d.set(d); this.loading.set(false); },
      error: e => { this.loading.set(false); this.notify.error(e); },
    });
    queueMicrotask(() => this.reload$.next());
  }

  pct(part: number, total: number): string {
    if (!total) return '0%';
    const p = (100 * part) / total;
    return (p < 0.1 && p > 0 ? '<0.1' : p.toFixed(1)) + '%';
  }
}
