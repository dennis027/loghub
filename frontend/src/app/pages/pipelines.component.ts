import { KeyValuePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/api.service';
import { formatBytes, formatNumber } from '../core/ui';
import { PageHeaderComponent, StatTileComponent, StatusChipComponent } from '../shared/ui.components';

@Component({
  selector: 'lh-pipelines',
  standalone: true,
  imports: [KeyValuePipe, MatButtonModule, MatCardModule, MatIconModule, PageHeaderComponent, StatTileComponent, StatusChipComponent],
  template: `
    <lh-page-header title="Log Pipelines" subtitle="Live counters from the Fluent Bit and Logstash monitoring APIs (since each process started)">
      <button mat-stroked-button (click)="load()"><mat-icon>refresh</mat-icon> Refresh</button>
    </lh-page-header>

    <mat-card class="pipeline-diagram">
      <mat-card-header><mat-card-title>Routing</mat-card-title>
        <mat-card-subtitle>Each event is routed by its log_route field; the default is Elasticsearch only (no duplication)</mat-card-subtitle></mat-card-header>
      <mat-card-content>
        @for (r of d()?.routes ?? []; track r.route) {
          <div class="route-row">
            <span class="route-name mono">{{ r.route }}</span>
            @for (step of r.path; track step; let last = $last) {
              <span class="route-step">{{ step }}</span>@if (!last) {<mat-icon class="route-arrow">arrow_forward</mat-icon>}
            }
            <span class="muted small">→ {{ r.consumers.join(', ') }}</span>
            @if (r.note) { <span class="warn-text small">{{ r.note }}</span> }
          </div>
        }
        <p class="muted small">Delivery is at-least-once: Fluent Bit buffers to disk and retries; Logstash uses a persisted queue and a
          dead-letter queue for documents Elasticsearch rejects. Event fingerprints are used as document ids so retries do not duplicate.</p>
      </mat-card-content>
    </mat-card>

    @if (d(); as d) {
      <section class="grid-2">
        <mat-card>
          <mat-card-header><mat-card-title>Fluent Bit (collector)</mat-card-title>
            <mat-card-subtitle>@if (d.fluent_bit.available) { v{{ d.fluent_bit.version }} } @else { unavailable }</mat-card-subtitle></mat-card-header>
          <mat-card-content>
            @if (d.fluent_bit.available) {
              <lh-status [status]="d.fluent_bit.healthy ? 'healthy' : 'degraded'" />
              <h4>Inputs</h4>
              <table class="data-table"><thead><tr><th>Input</th><th class="num">Records</th><th class="num">Bytes</th></tr></thead><tbody>
                @for (i of d.fluent_bit.inputs | keyvalue; track i.key) {
                  <tr><td class="mono">{{ i.key }}</td><td class="num">{{ num($any(i.value).records) }}</td><td class="num">{{ bytes($any(i.value).bytes) }}</td></tr>
                }
              </tbody></table>
              <h4>Outputs</h4>
              <table class="data-table"><thead><tr><th>Output</th><th class="num">Records</th><th class="num">Retries</th><th class="num">Errors</th><th class="num">Dropped</th></tr></thead><tbody>
                @for (o of d.fluent_bit.outputs | keyvalue; track o.key) {
                  <tr><td class="mono">{{ o.key }}</td><td class="num">{{ num($any(o.value).records) }}</td><td class="num">{{ $any(o.value).retries }}</td>
                    <td class="num" [class.warn-text]="$any(o.value).errors">{{ $any(o.value).errors }}</td><td class="num" [class.warn-text]="$any(o.value).dropped">{{ $any(o.value).dropped }}</td></tr>
                }
              </tbody></table>
            } @else { <div class="banner error">Fluent Bit monitoring API unreachable ({{ d.fluent_bit.message }}).</div> }
          </mat-card-content>
        </mat-card>

        <mat-card>
          <mat-card-header><mat-card-title>Logstash (processing)</mat-card-title>
            <mat-card-subtitle>@if (d.logstash.available) { v{{ d.logstash.version }} · heap {{ d.logstash.jvm_heap_percent }}% } @else { unavailable }</mat-card-subtitle></mat-card-header>
          <mat-card-content>
            @if (d.logstash.available) {
              <section class="stat-grid compact">
                <lh-stat label="Events in" [value]="num(d.logstash.events.in)" />
                <lh-stat label="Events out" [value]="num(d.logstash.events.out)" />
                <lh-stat label="Events lost" [value]="d.logstash.failures" [tone]="d.logstash.failures ? 'alert' : 'normal'" hint="DLQ overflow / expiry" />
                <lh-stat label="Duplicates / rejected" [value]="num(d.logstash.non_retryable_documents)" hint="409 = duplicate suppressed" />
                <lh-stat label="Retried requests" [value]="num(d.logstash.retried_requests)" hint="transient, delivered on retry" />
                <lh-stat label="Dead-letter queue" [value]="bytes(d.logstash.dead_letter_queue_bytes)"
                         [hint]="d.logstash.dlq_replay_running ? d.logstash.dlq_replayed_events + ' replayed automatically' : 'replay pipeline not running'"
                         [tone]="d.logstash.dlq_replay_running ? 'normal' : 'warn'" />
                <lh-stat label="Persisted queue" [value]="num(d.logstash.queue.events) + ' events'" [hint]="bytes(d.logstash.queue.size_bytes) + ' of ' + bytes(d.logstash.queue.max_bytes)" />
              </section>
              <div class="table-scroll"><table class="data-table"><thead><tr><th>Plugin</th><th>Kind</th><th class="num">In</th><th class="num">Out</th><th class="num">Failures / misses</th></tr></thead><tbody>
                @for (p of d.logstash.plugins; track p.id) {
                  <tr><td class="mono">{{ p.id }}</td><td>{{ p.kind }} · {{ p.name }}</td><td class="num">{{ num(p.events_in) }}</td>
                    <td class="num">{{ num(p.events_out) }}</td><td class="num" [class.warn-text]="p.failures">{{ p.failures ?? p.pattern_misses }}</td></tr>
                }
              </tbody></table></div>
            } @else { <div class="banner error">Logstash monitoring API unreachable ({{ d.logstash.message }}).</div> }
          </mat-card-content>
        </mat-card>
      </section>
    }
  `,
})
export class PipelinesComponent {
  private api = inject(ApiService);
  d = signal<any>(null);
  num = formatNumber;
  bytes = formatBytes;
  constructor() { this.load(); }
  load() { this.api.pipelines().subscribe(d => this.d.set(d)); }
}
