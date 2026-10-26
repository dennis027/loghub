import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { AlertRule, LogSource, NotificationChannel } from '../core/models';
import { LEVELS, Notify } from '../core/ui';
import { EmptyStateComponent, LevelBadgeComponent, PageHeaderComponent, StatusChipComponent } from '../shared/ui.components';

function blank(category: 'operational' | 'security'): AlertRule {
  return { name: '', description: '', category, rule_type: 'threshold', severity: 'warning', enabled: true, query: '',
    query_mode: 'simple', filters: {}, field_filters: [], source: null, window_minutes: 5, comparator: 'gt', threshold: 0,
    spike_factor: 3, min_count: 10, evaluation_interval_seconds: 60, cooldown_minutes: 15, channels: [] };
}

@Component({
  selector: 'lh-rules',
  standalone: true,
  imports: [DatePipe, FormsModule, MatButtonModule, MatCardModule, MatFormFieldModule, MatIconModule, MatInputModule,
    MatMenuModule, MatSelectModule, MatSlideToggleModule, MatTooltipModule, PageHeaderComponent, LevelBadgeComponent,
    StatusChipComponent, EmptyStateComponent],
  template: `
    <lh-page-header [title]="category === 'security' ? 'Detection Rules' : 'Alert Rules'"
                    [subtitle]="category === 'security' ? 'Security detections over indexed logs (auth abuse, injection, scanning)' : 'Thresholds, spikes, silence and storage conditions'">
      @if (auth.hasRole('editor')) {
        <button mat-stroked-button [matMenuTriggerFor]="tpl"><mat-icon>library_add</mat-icon> From template</button>
        <mat-menu #tpl="matMenu">
          @for (t of templates(); track t.key) { <button mat-menu-item (click)="fromTemplate(t)">{{ t.name }}</button> }
        </mat-menu>
        <button mat-flat-button color="primary" (click)="edit(null)"><mat-icon>add</mat-icon> New rule</button>
      }
    </lh-page-header>

    @if (draft(); as r) {
      <mat-card class="form-card">
        <mat-card-header><mat-card-title>{{ r.id ? 'Edit rule' : 'New rule' }}</mat-card-title></mat-card-header>
        <mat-card-content>
          <div class="form-grid">
            <mat-form-field class="span-2"><mat-label>Name</mat-label><input matInput [(ngModel)]="r.name" required /></mat-form-field>
            <mat-form-field><mat-label>Condition</mat-label>
              <mat-select [(ngModel)]="r.rule_type">
                <mat-option value="threshold">Event count crosses a threshold</mat-option>
                <mat-option value="spike">Sudden increase vs. previous window</mat-option>
                <mat-option value="absence">No events (source stopped sending)</mat-option>
                <mat-option value="storage">Elasticsearch disk usage %</mat-option>
              </mat-select></mat-form-field>
            <mat-form-field><mat-label>Severity</mat-label>
              <mat-select [(ngModel)]="r.severity">@for (s of severities; track s) { <mat-option [value]="s">{{ s }}</mat-option> }</mat-select></mat-form-field>
            <mat-form-field class="span-2"><mat-label>Description</mat-label><input matInput [(ngModel)]="r.description" /></mat-form-field>
            @if (r.rule_type !== 'storage') {
              <mat-form-field class="span-2"><mat-label>Query ({{ r.query_mode }})</mat-label><input matInput class="mono" [(ngModel)]="r.query" /></mat-form-field>
              <mat-form-field><mat-label>Syntax</mat-label>
                <mat-select [(ngModel)]="r.query_mode"><mat-option value="simple">Simple</mat-option><mat-option value="lucene">Lucene</mat-option></mat-select></mat-form-field>
              <mat-form-field><mat-label>Levels</mat-label>
                <mat-select multiple [ngModel]="r.filters['level'] || []" (ngModelChange)="setFilter(r, 'level', $event)">
                  @for (l of levels; track l) { <mat-option [value]="l">{{ l }}</mat-option> }</mat-select></mat-form-field>
              <mat-form-field><mat-label>Services (comma-separated)</mat-label>
                <input matInput [ngModel]="(r.filters['service'] || []).join(', ')" (ngModelChange)="setFilter(r, 'service', split($event))" /></mat-form-field>
              <mat-form-field><mat-label>Event types (comma-separated)</mat-label>
                <input matInput [ngModel]="(r.filters['event_type'] || []).join(', ')" (ngModelChange)="setFilter(r, 'event_type', split($event))" /></mat-form-field>
              <mat-form-field><mat-label>Restrict to source</mat-label>
                <mat-select [(ngModel)]="r.source"><mat-option [value]="null">Any</mat-option>
                  @for (s of sources(); track s.id) { <mat-option [value]="s.id">{{ s.name }}</mat-option> }</mat-select></mat-form-field>
              <mat-form-field><mat-label>Window (minutes)</mat-label><input matInput type="number" [(ngModel)]="r.window_minutes" /></mat-form-field>
            }
            @if (r.rule_type === 'threshold' || r.rule_type === 'storage') {
              <mat-form-field><mat-label>Comparator</mat-label>
                <mat-select [(ngModel)]="r.comparator"><mat-option value="gt">&gt;</mat-option><mat-option value="gte">≥</mat-option>
                  <mat-option value="lt">&lt;</mat-option><mat-option value="lte">≤</mat-option></mat-select></mat-form-field>
              <mat-form-field><mat-label>{{ r.rule_type === 'storage' ? 'Disk used %' : 'Event count' }}</mat-label><input matInput type="number" [(ngModel)]="r.threshold" /></mat-form-field>
            }
            @if (r.rule_type === 'spike') {
              <mat-form-field><mat-label>Spike factor (×)</mat-label><input matInput type="number" step="0.5" [(ngModel)]="r.spike_factor" /></mat-form-field>
              <mat-form-field><mat-label>Minimum events</mat-label><input matInput type="number" [(ngModel)]="r.min_count" /></mat-form-field>
            }
            <mat-form-field><mat-label>Evaluate every (s)</mat-label><input matInput type="number" min="30" [(ngModel)]="r.evaluation_interval_seconds" /></mat-form-field>
            <mat-form-field><mat-label>Cooldown after resolve (min)</mat-label><input matInput type="number" [(ngModel)]="r.cooldown_minutes" /></mat-form-field>
            <mat-form-field class="span-2"><mat-label>Notify channels</mat-label>
              <mat-select multiple [(ngModel)]="r.channels">@for (c of channels(); track c.id) { <mat-option [value]="c.id">{{ c.name }}</mat-option> }</mat-select></mat-form-field>
            <mat-slide-toggle [(ngModel)]="r.enabled">Enabled</mat-slide-toggle>
          </div>
          <div class="form-actions">
            <button mat-button (click)="draft.set(null)">Cancel</button>
            <button mat-flat-button color="primary" (click)="save(r)" [disabled]="!r.name">Save</button>
          </div>
        </mat-card-content>
      </mat-card>
    }

    <mat-card>
      <table class="data-table">
        <thead><tr><th>Rule</th><th>Severity</th><th>Condition</th><th>State</th><th class="num">Last value</th>
          <th>Last evaluated</th><th class="num">Open</th><th>Enabled</th><th></th></tr></thead>
        <tbody>
          @for (r of rules(); track r.id) {
            <tr>
              <td><strong>{{ r.name }}</strong><div class="muted small">{{ r.description }}</div></td>
              <td><lh-level [level]="r.severity" /></td>
              <td class="small">{{ describe(r) }}</td>
              <td><lh-status [status]="stateChip(r.last_state)" [label]="r.last_state === 'cooldown' ? 'cooldown' : r.last_state"
                             [matTooltip]="r.last_state === 'cooldown' ? 'Condition holds, but re-firing is suppressed for ' + r.cooldown_minutes + ' min after the last resolution' : ''" />@if (r.last_error) { <div class="small warn-text">{{ r.last_error }}</div> }</td>
              <td class="num">{{ r.last_value ?? '—' }}</td>
              <td class="muted">{{ r.last_evaluated_at ? (r.last_evaluated_at | date: 'short') : 'never' }}</td>
              <td class="num">{{ r.open_events }}</td>
              <td>{{ r.enabled ? 'yes' : 'no' }}</td>
              <td class="actions">
                @if (auth.hasRole('editor')) {
                  <button mat-icon-button (click)="runPreview(r)" matTooltip="Dry run" aria-label="Dry run"><mat-icon>science</mat-icon></button>
                  <button mat-icon-button (click)="evaluateNow(r)" matTooltip="Evaluate now (may notify)" aria-label="Evaluate now"><mat-icon>play_circle</mat-icon></button>
                  <button mat-icon-button (click)="edit(r)" matTooltip="Edit" aria-label="Edit"><mat-icon>edit</mat-icon></button>
                  <button mat-icon-button (click)="remove(r)" matTooltip="Delete" aria-label="Delete"><mat-icon>delete</mat-icon></button>
                }
              </td>
            </tr>
          } @empty {
            <tr><td colspan="9"><lh-empty icon="rule" title="No rules yet">Start from a template above.</lh-empty></td></tr>
          }
        </tbody>
      </table>
    </mat-card>
  `,
})
export class RulesComponent implements OnInit {
  private api = inject(ApiService);
  private notify = inject(Notify);
  private route = inject(ActivatedRoute);
  auth = inject(AuthService);
  category: 'operational' | 'security' = 'operational';
  rules = signal<AlertRule[]>([]);
  templates = signal<any[]>([]);
  channels = signal<NotificationChannel[]>([]);
  sources = signal<LogSource[]>([]);
  draft = signal<AlertRule | null>(null);
  severities = ['info', 'warning', 'error', 'critical'];
  levels = LEVELS;

  ngOnInit() {
    this.category = this.route.snapshot.data['category'] ?? 'operational';
    this.load();
    this.api.rules.action<any[]>(null, 'templates', {}, 'get')
      .subscribe(t => this.templates.set(t.filter(x => x.category === this.category)));
    this.api.channels.list().subscribe(r => this.channels.set(r.results));
    this.api.sources.list({ page_size: 200 }).subscribe(r => this.sources.set(r.results));
  }

  load() { this.api.rules.list({ category: this.category, page_size: 200 }).subscribe(r => this.rules.set(r.results)); }
  split(v: string) { return v.split(',').map(s => s.trim()).filter(Boolean); }
  setFilter(r: AlertRule, key: string, values: string[]) {
    const f = { ...r.filters };
    if (values.length) f[key] = values; else delete f[key];
    r.filters = f;
  }

  stateChip(state?: string) {
    return ({ ok: 'healthy', firing: 'firing', cooldown: 'acknowledged', error: 'error' } as Record<string, string>)[state ?? ''] ?? 'unknown';
  }

  describe(r: AlertRule) {
    const sym = { gt: '>', gte: '≥', lt: '<', lte: '≤' }[r.comparator];
    switch (r.rule_type) {
      case 'threshold': return `count ${sym} ${r.threshold} in ${r.window_minutes}m${r.query ? ` where “${r.query}”` : ''}`;
      case 'spike': return `≥ ${r.spike_factor}× previous ${r.window_minutes}m (min ${r.min_count})`;
      case 'absence': return `no events for ${r.window_minutes}m`;
      case 'storage': return `ES disk ${sym} ${r.threshold}%`;
    }
  }

  edit(r: AlertRule | null) {
    this.draft.set(r ? structuredClone(r) : { ...blank(this.category), channels: this.channels().slice(0, 1).map(c => c.id!) });
  }

  fromTemplate(t: any) {
    const { key, ...fields } = t;
    this.edit(null);
    this.draft.update(d => ({ ...d!, ...fields }));
  }

  save(r: AlertRule) {
    const { id, last_evaluated_at, last_value, last_state, last_error, open_events, ...body } = r;
    const req = id ? this.api.rules.update(id, body) : this.api.rules.create(body);
    req.subscribe({
      next: () => { this.draft.set(null); this.notify.ok('Rule saved'); this.load(); },
      error: e => this.notify.error(e),
    });
  }

  runPreview(r: AlertRule) {
    this.api.rules.action<{ firing: boolean; summary: string }>(r.id!, 'preview').subscribe({
      next: p => this.notify.ok(`${p.firing ? 'Would fire' : 'Would not fire'}: ${p.summary}`),
      error: e => this.notify.error(e),
    });
  }

  evaluateNow(r: AlertRule) {
    this.api.rules.action<{ event: any }>(r.id!, 'evaluate').subscribe({
      next: res => { this.notify.ok(res.event ? `Alert firing: ${res.event.message}` : 'Condition not met'); this.load(); },
      error: e => this.notify.error(e),
    });
  }

  remove(r: AlertRule) {
    if (!confirm(`Delete rule "${r.name}"?`)) return;
    this.api.rules.remove(r.id!).subscribe({ next: () => this.load(), error: e => this.notify.error(e) });
  }
}
