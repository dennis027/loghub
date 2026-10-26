import { Component, inject, signal } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { forkJoin } from 'rxjs';
import { ApiService } from '../core/api.service';
import { formatBytes } from '../core/ui';
import { metricLinesOption } from '../shared/charts';
import { ChartComponent, PageHeaderComponent, StatTileComponent, StatusChipComponent } from '../shared/ui.components';

const SERIES = {
  cpu: '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)',
  mem: '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100',
  load: 'node_load1',
  ingest: 'sum(rate(fluentbit_input_records_total[2m]))',
};

@Component({
  selector: 'lh-infrastructure',
  standalone: true,
  imports: [MatCardModule, PageHeaderComponent, StatTileComponent, ChartComponent, StatusChipComponent],
  template: `
    <lh-page-header title="Infrastructure Monitoring" subtitle="Host metrics from Prometheus node-exporter; cluster state from Elasticsearch" />
    @if (d(); as d) {
      @if (!d.prometheus_available) { <div class="banner warn">{{ d.prometheus_error }}</div> }
      <section class="stat-grid">
        <lh-stat label="CPU" icon="memory" [value]="pct(d.metrics.cpu_percent)" [hint]="(d.metrics.cpu_count ?? '—') + ' cores'" />
        <lh-stat label="Memory" icon="sd_storage" [value]="pct(d.metrics.memory_percent)" [hint]="bytes(d.metrics.memory_total_bytes) + ' total'" />
        <lh-stat label="Load (1m)" icon="speed" [value]="d.metrics.load1 ?? '—'" />
        <lh-stat label="Uptime" icon="schedule" [value]="uptime(d.metrics.uptime_seconds)" />
      </section>
      <section class="grid-2">
        <mat-card><mat-card-header><mat-card-title>CPU usage</mat-card-title></mat-card-header>
          <mat-card-content><lh-chart [options]="charts().cpu" [height]="200" /></mat-card-content></mat-card>
        <mat-card><mat-card-header><mat-card-title>Memory used</mat-card-title></mat-card-header>
          <mat-card-content><lh-chart [options]="charts().mem" [height]="200" /></mat-card-content></mat-card>
        <mat-card><mat-card-header><mat-card-title>Load average (1m)</mat-card-title></mat-card-header>
          <mat-card-content><lh-chart [options]="charts().load" [height]="200" /></mat-card-content></mat-card>
        <mat-card><mat-card-header><mat-card-title>Collector ingest rate (records/s)</mat-card-title></mat-card-header>
          <mat-card-content><lh-chart [options]="charts().ingest" [height]="200" /></mat-card-content></mat-card>
        <mat-card><mat-card-header><mat-card-title>Disks</mat-card-title></mat-card-header>
          <mat-card-content>
            <table class="data-table"><tbody>
              @for (disk of d.disks; track disk.mountpoint) {
                <tr><td class="mono">{{ disk.mountpoint }}</td>
                  <td><div class="meter"><div class="meter-fill" [style.width.%]="disk.used_percent" [class.hot]="disk.used_percent > 85"></div></div></td>
                  <td class="num">{{ disk.used_percent }}%</td></tr>
              } @empty { <tr><td class="muted">No filesystem metrics.</td></tr> }
            </tbody></table>
          </mat-card-content></mat-card>
        <mat-card><mat-card-header><mat-card-title>Elasticsearch</mat-card-title></mat-card-header>
          <mat-card-content>
            <p><lh-status [status]="d.elasticsearch.status" /> {{ d.elasticsearch.message }}</p>
            <table class="data-table"><tbody>
              <tr><td>Version</td><td>{{ d.elasticsearch.version }}</td></tr>
              <tr><td>Nodes</td><td>{{ d.elasticsearch.nodes }}</td></tr>
              <tr><td>Active / unassigned shards</td><td>{{ d.elasticsearch.active_shards }} / {{ d.elasticsearch.unassigned_shards }}</td></tr>
              <tr><td>Disk used</td><td>{{ d.elasticsearch.storage?.disk?.used_percent ?? '—' }}%</td></tr>
              <tr><td>This organization's data</td><td>{{ bytes(d.elasticsearch.storage?.data_stream?.store_size_bytes) }}
                ({{ d.elasticsearch.storage?.data_stream?.backing_indices ?? 0 }} backing indices)</td></tr>
            </tbody></table>
          </mat-card-content></mat-card>
      </section>
    }
  `,
})
export class InfrastructureComponent {
  private api = inject(ApiService);
  d = signal<any>(null);
  charts = signal<{ cpu: any; mem: any; load: any; ingest: any }>({ cpu: {}, mem: {}, load: {}, ingest: {} });
  bytes = formatBytes;

  constructor() {
    this.api.infrastructure().subscribe(d => this.d.set(d));
    forkJoin(Object.fromEntries(Object.entries(SERIES).map(([k, q]) => [k, this.api.metricsRange(q, '6h')]))).subscribe({
      next: (r: Record<string, any>) => this.charts.set({
        cpu: metricLinesOption(r['cpu'].series, '%'), mem: metricLinesOption(r['mem'].series, '%'),
        load: metricLinesOption(r['load'].series), ingest: metricLinesOption(r['ingest'].series),
      }),
      error: () => { /* banner from the snapshot call explains Prometheus being unavailable */ },
    });
  }

  pct(v: number | null) { return v === null || v === undefined ? '—' : `${v.toFixed(1)}%`; }
  uptime(s: number | null) {
    if (!s) return '—';
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600);
    return d ? `${d}d ${h}h` : `${h}h ${Math.floor((s % 3600) / 60)}m`;
  }
}
