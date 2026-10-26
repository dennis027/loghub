import { DatePipe } from '@angular/common';
import { Component, OnChanges, inject, input, signal } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import type { EChartsOption } from 'echarts';
import { ApiService } from '../core/api.service';
import { Bucket, LogHit, Widget } from '../core/models';
import { errorMessage, formatNumber } from '../core/ui';
import { barOption, donutOption, metricLinesOption, timeSeriesOption } from './charts';
import { ChartComponent, LevelBadgeComponent } from './ui.components';

/** Flat search params for a widget; tolerates the legacy nested {filters: {...}} shape. */
export function widgetQuery(w: Widget): Record<string, unknown> {
  const { filters, ...rest } = (w.query ?? {}) as Record<string, any>;
  return { ...rest, ...(filters ?? {}) };
}

/** Renders one dashboard widget from live data (log aggregations or PromQL). */
@Component({
  selector: 'lh-widget',
  standalone: true,
  imports: [DatePipe, MatCardModule, MatProgressBarModule, ChartComponent, LevelBadgeComponent],
  template: `
    <mat-card class="widget">
      <mat-card-header><mat-card-title>{{ widget().title }}</mat-card-title></mat-card-header>
      @if (loading()) { <mat-progress-bar mode="indeterminate" /> }
      <mat-card-content>
        @if (error()) {
          <div class="widget-error">{{ error() }}</div>
        } @else {
          @switch (widget().type) {
            @case ('stat') { <div class="stat-value big">{{ stat() }}</div> }
            @case ('table') {
              <table class="data-table">
                <thead><tr><th>{{ widget().agg?.field }}</th><th class="num">Events</th>
                  @if (widget().agg?.metric) { <th class="num">{{ widget().agg?.metric }} {{ widget().agg?.metric_field }}</th> }</tr></thead>
                <tbody>
                  @for (b of buckets(); track b.key) {
                    <tr><td class="mono wrap">{{ b.key }}</td><td class="num">{{ b.count }}</td>
                      @if (widget().agg?.metric) { <td class="num">{{ fmt(b.value) }}</td> }</tr>
                  } @empty { <tr><td colspan="3" class="muted">No data in range.</td></tr> }
                </tbody>
              </table>
            }
            @case ('logs') {
              <div class="widget-logs">
                @for (h of logs(); track h.id) {
                  <div class="live-line"><span class="mono muted">{{ h.timestamp | date: 'MMM d HH:mm:ss' }}</span>
                    <lh-level [level]="h.level" /><span class="svc">{{ h.service }}</span><span class="mono msg">{{ h.message }}</span></div>
                } @empty { <div class="muted">No matching events.</div> }
              </div>
            }
            @default {
              @if (empty()) { <div class="muted pad">No data in range.</div> }
              @else { <lh-chart [options]="options()" [height]="220" /> }
            }
          }
        }
      </mat-card-content>
    </mat-card>
  `,
})
export class WidgetComponent implements OnChanges {
  widget = input.required<Widget>();
  range = input('24h');
  refresh = input(0);
  private api = inject(ApiService);

  loading = signal(false);
  error = signal('');
  stat = signal('—');
  buckets = signal<Bucket[]>([]);
  logs = signal<LogHit[]>([]);
  options = signal<EChartsOption>({});
  empty = signal(false);
  fmt = formatNumber;

  ngOnChanges() { this.load(); }

  private load() {
    const w = this.widget();
    this.loading.set(true);
    this.error.set('');
    const done = () => this.loading.set(false);
    const fail = (e: unknown) => { this.error.set(errorMessage(e)); done(); };

    if (w.source === 'prometheus') {
      this.api.metricsRange(w.promql ?? '', this.range() === '30d' ? '7d' : this.range()).subscribe({
        next: r => { this.empty.set(!r.series.length); this.options.set(metricLinesOption(r.series, w.unit ?? '')); done(); },
        error: fail,
      });
      return;
    }
    const q = { ...widgetQuery(w), range: this.range() };
    if (w.type === 'logs') {
      this.api.search({ ...q, size: 15 }).subscribe({ next: r => { this.logs.set(r.hits); done(); }, error: fail });
      return;
    }
    const agg = w.agg ?? { type: w.type === 'stat' ? 'metric' : w.type === 'timeseries' ? 'histogram' : 'terms', field: 'service' };
    this.api.aggregate<Record<string, any>>(q, { w: agg as never }).subscribe({
      next: r => {
        const data = r['w'];
        if (w.type === 'stat') {
          const value = agg.type === 'metric' && !agg.metric ? r['_total'] : data.value;
          this.stat.set(value === null || value === undefined ? '—' : formatNumber(Math.round(value * 100) / 100) + (w.unit ? ` ${w.unit}` : ''));
        } else if (w.type === 'timeseries') {
          this.empty.set(!data.buckets.some((b: any) => b.count));
          this.options.set(timeSeriesOption(data));
        } else {
          this.buckets.set(data.buckets);
          this.empty.set(!data.buckets.length);
          this.options.set(w.type === 'pie' ? donutOption(data.buckets) : barOption(data.buckets));
        }
        done();
      },
      error: fail,
    });
  }
}
