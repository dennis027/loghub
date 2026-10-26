import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, Router } from '@angular/router';
import { forkJoin } from 'rxjs';
import { ApiService, downloadBlob } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { FieldFilter, Histogram, LogHit, LogQueryParams, SavedSearch, SearchResponse } from '../core/models';
import { LEVELS, Notify, TIME_RANGES } from '../core/ui';
import { timeSeriesOption } from '../shared/charts';
import {
  ChartComponent, CopyButtonComponent, EmptyStateComponent, JsonViewComponent, LevelBadgeComponent, PageHeaderComponent,
} from '../shared/ui.components';

const FILTER_FIELDS = [
  { key: 'service', label: 'Application / service' },
  { key: 'environment', label: 'Environment' },
  { key: 'hostname', label: 'Host' },
  { key: 'container', label: 'Container' },
  { key: 'source_id', label: 'Source' },
  { key: 'collector', label: 'Collector' },
] as const;
type FilterKey = (typeof FILTER_FIELDS)[number]['key'];
const OPS = [
  { v: 'eq', l: '=' }, { v: 'neq', l: '≠' }, { v: 'contains', l: 'contains' }, { v: 'gt', l: '>' }, { v: 'gte', l: '≥' },
  { v: 'lt', l: '<' }, { v: 'lte', l: '≤' }, { v: 'exists', l: 'exists' }, { v: 'missing', l: 'missing' },
];
const HIDDEN_DETAIL_FIELDS = new Set(['message', 'raw']);

@Component({
  selector: 'lh-log-explorer',
  standalone: true,
  imports: [DatePipe, FormsModule, MatButtonModule, MatButtonToggleModule, MatCardModule, MatChipsModule, MatFormFieldModule,
    MatIconModule, MatInputModule, MatMenuModule, MatProgressBarModule, MatSelectModule, MatTooltipModule,
    PageHeaderComponent, ChartComponent, LevelBadgeComponent, JsonViewComponent, CopyButtonComponent, EmptyStateComponent],
  template: `
    <lh-page-header title="Log Explorer" subtitle="Search indexed events across every source">
      <button mat-stroked-button [matMenuTriggerFor]="savedMenu"><mat-icon>bookmarks</mat-icon> Saved searches</button>
      <mat-menu #savedMenu="matMenu">
        @for (s of saved(); track s.id) {
          <button mat-menu-item (click)="applySaved(s)"><mat-icon>search</mat-icon>{{ s.name }}</button>
        } @empty { <div class="menu-empty">No saved searches yet</div> }
      </mat-menu>
      @if (auth.hasRole('analyst')) {
        <button mat-stroked-button (click)="saveSearch()"><mat-icon>bookmark_add</mat-icon> Save</button>
        <button mat-stroked-button [matMenuTriggerFor]="exportMenu" [disabled]="provider !== 'elasticsearch'"
                matTooltip="Exports run through Elasticsearch (max 10,000 rows)"><mat-icon>download</mat-icon> Export</button>
        <mat-menu #exportMenu="matMenu">
          <button mat-menu-item (click)="export('csv')">CSV</button>
          <button mat-menu-item (click)="export('json')">JSON</button>
        </mat-menu>
      }
    </lh-page-header>

    <mat-card class="query-card">
      <form class="query-row" (ngSubmit)="search()">
        <mat-form-field class="grow">
          <mat-label>{{ mode === 'lucene' ? 'Lucene / Kibana query' : 'Search messages' }}</mat-label>
          <mat-icon matPrefix>search</mat-icon>
          <input matInput name="q" [(ngModel)]="q" [placeholder]="mode === 'lucene' ? 'level:error AND service:api AND http.status:>=500' : 'timeout -healthcheck &quot;payment failed&quot;'" />
        </mat-form-field>
        <mat-button-toggle-group name="mode" [(ngModel)]="mode" aria-label="Query syntax">
          <mat-button-toggle value="simple" matTooltip="Forgiving text search: AND/OR (|), -exclude, &quot;phrases&quot;, prefix*">Simple</mat-button-toggle>
          <mat-button-toggle value="lucene" matTooltip="Lucene syntax (as in Kibana): field:value, ranges, booleans">Lucene</mat-button-toggle>
        </mat-button-toggle-group>
        <mat-form-field class="w-180">
          <mat-label>Engine</mat-label>
          <mat-select name="provider" [(ngModel)]="provider">
            <mat-option value="elasticsearch">Elasticsearch</mat-option>
            <mat-option value="graylog">Graylog</mat-option>
          </mat-select>
        </mat-form-field>
        <mat-form-field class="w-180">
          <mat-label>Time range</mat-label>
          <mat-select name="range" [(ngModel)]="range">
            @for (r of ranges; track r.value) { <mat-option [value]="r.value">{{ r.label }}</mat-option> }
          </mat-select>
        </mat-form-field>
        <button mat-flat-button color="primary" type="submit">Search</button>
      </form>

      <div class="filter-row">
        <mat-form-field class="w-160">
          <mat-label>Level</mat-label>
          <mat-select multiple [(ngModel)]="levels" (selectionChange)="search()">
            @for (l of levelOptions; track l) { <mat-option [value]="l">{{ l }}</mat-option> }
          </mat-select>
        </mat-form-field>
        @for (f of filterFields; track f.key) {
          <mat-form-field class="w-180">
            <mat-label>{{ f.label }}</mat-label>
            <mat-select multiple [ngModel]="filters()[f.key]" (ngModelChange)="setFilter(f.key, $event); search()"
                        (openedChange)="$event && loadValues(f.key)">
              @for (v of values()[f.key] ?? []; track v.key) {
                <mat-option [value]="v.key">{{ v.key }} <span class="muted">({{ v.count }})</span></mat-option>
              }
              @for (v of selectedNotLoaded(f.key); track v) { <mat-option [value]="v">{{ v }}</mat-option> }
            </mat-select>
          </mat-form-field>
        }
        <button mat-stroked-button type="button" [matMenuTriggerFor]="ffMenu"><mat-icon>filter_alt</mat-icon> Field filter</button>
        <mat-menu #ffMenu="matMenu" class="ff-menu">
          <div class="ff-form" tabindex="-1" (click)="$event.stopPropagation()" (keydown)="$event.stopPropagation()">
            <mat-form-field><mat-label>Field</mat-label><input matInput [(ngModel)]="ff.field" placeholder="http.status" /></mat-form-field>
            <mat-form-field><mat-label>Operator</mat-label>
              <mat-select [(ngModel)]="ff.op">@for (o of ops; track o.v) { <mat-option [value]="o.v">{{ o.l }}</mat-option> }</mat-select>
            </mat-form-field>
            @if (ff.op !== 'exists' && ff.op !== 'missing') {
              <mat-form-field><mat-label>Value</mat-label><input matInput [(ngModel)]="ff.value" /></mat-form-field>
            }
            <button mat-flat-button color="primary" (click)="addFieldFilter()" [disabled]="!ff.field">Add</button>
          </div>
        </mat-menu>
      </div>
      @if (fieldFilters().length) {
        <mat-chip-set aria-label="Field filters">
          @for (f of fieldFilters(); track $index) {
            <mat-chip (removed)="removeFieldFilter($index)">
              <span class="mono">{{ f.field }} {{ opLabel(f.op) }} {{ f.value ?? '' }}</span>
              <button matChipRemove aria-label="Remove filter"><mat-icon>cancel</mat-icon></button>
            </mat-chip>
          }
        </mat-chip-set>
      }
    </mat-card>

    @if (loading()) { <mat-progress-bar mode="indeterminate" /> }
    @if (error()) { <div class="banner error" role="alert">{{ error() }}</div> }

    @if (result(); as r) {
      <div class="result-meta">
        <span class="engine-badge" [class.graylog]="r.provider === 'graylog'">
          <mat-icon inline>{{ r.provider === 'graylog' ? 'hub' : 'storage' }}</mat-icon> Executed by {{ r.provider === 'graylog' ? 'Graylog' : 'Elasticsearch' }} via LogHub API
        </span>
        <span><strong>{{ r.total_relation === 'gte' ? '≥ ' : '' }}{{ r.total.toLocaleString() }}</strong> events · {{ r.took_ms }} ms</span>
        @if (r.timed_out) { <span class="warn-text">Query timed out — results are partial.</span> }
        <span class="spacer"></span>
        @if (r.external_url) {
          <a mat-button [href]="r.external_url" target="_blank" rel="noopener noreferrer">
            <mat-icon>open_in_new</mat-icon> Open in {{ r.provider === 'graylog' ? 'Graylog' : 'Kibana' }}
          </a>
        }
      </div>

      @if (histogram(); as h) {
        <mat-card class="histogram-card"><lh-chart [options]="histOptions()" [height]="150" /></mat-card>
      }

      @if (hits().length) {
        <div class="log-table" role="table" aria-label="Log events">
          <div class="log-row log-head" role="row">
            <span role="columnheader">Time</span><span role="columnheader">Level</span>
            <span role="columnheader">Service</span><span role="columnheader">Host / container</span>
            <span role="columnheader">Message</span>
          </div>
          @for (hit of hits(); track hit.id) {
            <div class="log-row" role="row" tabindex="0" [class.expanded]="expanded() === hit.id"
                 (click)="toggle(hit)" (keydown.enter)="toggle(hit)">
              <span class="mono nowrap">{{ hit.timestamp | date: 'MMM d, HH:mm:ss.SSS' }}</span>
              <span><lh-level [level]="hit.level" /></span>
              <span class="ellipsis">{{ hit.service }}</span>
              <span class="ellipsis muted">{{ hit.container || hit.hostname }}</span>
              <span class="mono message">@if (hit.demo) {<span class="demo-tag">demo</span>}{{ hit.message }}</span>
            </div>
            @if (expanded() === hit.id) {
              <div class="log-detail">
                <div class="detail-actions">
                  <lh-copy [text]="hit.message" label="Copy message" />
                  @if (provider === 'elasticsearch') {
                    <button mat-button (click)="showContext(hit)"><mat-icon>unfold_more</mat-icon> Surrounding logs</button>
                  }
                  @if (hit.trace_id) {
                    <button mat-button (click)="filterTrace(hit.trace_id)"><mat-icon>timeline</mat-icon> Related logs (trace)</button>
                  }
                  @if (hit.service) {
                    <button mat-button (click)="setFilter('service', [hit.service]); search()"><mat-icon>filter_alt</mat-icon> Only {{ hit.service }}</button>
                  }
                </div>
                <pre class="message-full">{{ hit.message }}</pre>
                <table class="field-table">
                  @for (f of fields(hit); track f[0]) {
                    <tr><th class="mono">{{ f[0] }}</th><td class="mono wrap">{{ f[1] }}</td>
                      <td><button mat-icon-button (click)="addEq(f[0], f[1])" matTooltip="Filter on this value" aria-label="Filter on this value"><mat-icon>add_circle_outline</mat-icon></button></td></tr>
                  }
                </table>
                <details><summary>Raw JSON</summary><lh-json [value]="hit.source" /></details>
                @if (context().length) {
                  <h4>Surrounding events (±2 min, same service/host)</h4>
                  <div class="context-list">
                    @for (c of context(); track c.id) {
                      <div class="context-row" [class.current]="c.id === hit.id">
                        <span class="mono">{{ c.timestamp | date: 'HH:mm:ss.SSS' }}</span> <lh-level [level]="c.level" />
                        <span class="mono">{{ c.message }}</span>
                      </div>
                    }
                  </div>
                }
              </div>
            }
          }
        </div>
        @if (cursor()) {
          <div class="load-more"><button mat-stroked-button (click)="loadMore()" [disabled]="loading()">Load older events</button></div>
        }
      } @else if (!loading()) {
        <lh-empty icon="search_off" title="No events match">Widen the time range, remove filters, or check that sources are sending logs.</lh-empty>
      }
    }
  `,
})
export class LogExplorerComponent implements OnInit {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private notify = inject(Notify);
  auth = inject(AuthService);

  ranges = TIME_RANGES;
  levelOptions = LEVELS;
  filterFields = FILTER_FIELDS;
  ops = OPS;

  q = '';
  mode: 'simple' | 'lucene' = 'simple';
  provider = 'elasticsearch';
  range = '1h';
  levels: string[] = [];
  filters = signal<Partial<Record<FilterKey, string[]>>>({});
  fieldFilters = signal<FieldFilter[]>([]);
  values = signal<Partial<Record<FilterKey, { key: string; count: number }[]>>>({});
  ff: { field: string; op: string; value: string } = { field: '', op: 'eq', value: '' };

  result = signal<SearchResponse | null>(null);
  hits = signal<LogHit[]>([]);
  cursor = signal<string | null>(null);
  histogram = signal<Histogram | null>(null);
  histOptions = computed(() => (this.histogram() ? timeSeriesOption(this.histogram()!) : {}));
  loading = signal(false);
  error = signal('');
  expanded = signal<string | null>(null);
  context = signal<LogHit[]>([]);
  saved = signal<SavedSearch[]>([]);

  ngOnInit() {
    const p = this.route.snapshot.queryParamMap;
    this.q = p.get('q') ?? '';
    this.mode = (p.get('mode') as 'simple' | 'lucene') ?? 'simple';
    this.provider = p.get('provider') ?? 'elasticsearch';
    this.range = p.get('range') ?? this.auth.user()?.preferences.default_time_range ?? '1h';
    this.levels = p.get('level')?.split(',').filter(Boolean) ?? [];
    const f: Partial<Record<FilterKey, string[]>> = {};
    for (const { key } of FILTER_FIELDS) {
      const v = p.get(key);
      if (v) f[key] = v.split(',');
    }
    this.filters.set(f);
    try { this.fieldFilters.set(JSON.parse(p.get('ff') ?? '[]')); } catch { /* ignore malformed */ }
    this.api.savedSearches.list().subscribe(r => this.saved.set(r.results));
    this.search();
  }

  private query(): LogQueryParams {
    return {
      q: this.q, mode: this.mode, provider: this.provider, range: this.range, level: this.levels,
      ...this.filters(), field_filters: this.fieldFilters(), size: 100,
    } as LogQueryParams;
  }

  search() {
    const q = this.query();
    this.syncUrl();
    this.loading.set(true);
    this.error.set('');
    this.expanded.set(null);
    const histogram$ = this.provider === 'elasticsearch'
      ? this.api.aggregate<{ h: Histogram }>(q, { h: { type: 'histogram', split_by: 'level' } })
      : null;
    forkJoin(histogram$ ? [this.api.search(q), histogram$] : [this.api.search(q)]).subscribe({
      next: ([res, agg]: any[]) => {
        this.result.set(res);
        this.hits.set(res.hits);
        this.cursor.set(res.cursor);
        this.histogram.set(agg ? agg.h : null);
        this.loading.set(false);
      },
      error: err => {
        this.loading.set(false);
        this.result.set(null);
        this.error.set(err?.error?.error?.message ?? 'Search failed.');
      },
    });
  }

  loadMore() {
    this.loading.set(true);
    this.api.search({ ...this.query(), cursor: this.cursor() }).subscribe({
      next: res => {
        this.hits.update(h => [...h, ...res.hits]);
        this.cursor.set(res.cursor);
        this.loading.set(false);
      },
      error: e => { this.loading.set(false); this.notify.error(e); },
    });
  }

  private syncUrl() {
    const qp: Record<string, string | null> = {
      q: this.q || null, mode: this.mode === 'simple' ? null : this.mode,
      provider: this.provider === 'elasticsearch' ? null : this.provider, range: this.range,
      level: this.levels.join(',') || null,
      ff: this.fieldFilters().length ? JSON.stringify(this.fieldFilters()) : null,
    };
    for (const { key } of FILTER_FIELDS) qp[key] = this.filters()[key]?.join(',') || null;
    this.router.navigate([], { queryParams: qp, replaceUrl: true });
  }

  loadValues(key: FilterKey) {
    if (this.values()[key]) return;
    this.api.fieldValues(key, this.range).subscribe({
      next: r => this.values.update(v => ({ ...v, [key]: r.values })),
      error: () => this.values.update(v => ({ ...v, [key]: [] })),
    });
  }

  selectedNotLoaded(key: FilterKey): string[] {
    const loaded = new Set((this.values()[key] ?? []).map(v => v.key));
    return (this.filters()[key] ?? []).filter(v => !loaded.has(v));
  }

  setFilter(key: FilterKey | string, value: string[]) {
    this.filters.update(f => ({ ...f, [key]: value }));
  }

  addFieldFilter() {
    const { field, op, value } = this.ff;
    const numeric = value !== '' && !isNaN(Number(value)) && ['gt', 'gte', 'lt', 'lte'].includes(op);
    this.fieldFilters.update(f => [...f, { field: field.trim(), op, ...(op === 'exists' || op === 'missing' ? {} : { value: numeric ? Number(value) : value }) }]);
    this.ff = { field: '', op: 'eq', value: '' };
    this.search();
  }

  addEq(field: string, value: string) {
    this.fieldFilters.update(f => [...f, { field, op: 'eq', value }]);
    this.search();
  }

  removeFieldFilter(i: number) {
    this.fieldFilters.update(f => f.filter((_, idx) => idx !== i));
    this.search();
  }

  opLabel(op: string) { return OPS.find(o => o.v === op)?.l ?? op; }

  toggle(hit: LogHit) {
    this.context.set([]);
    this.expanded.set(this.expanded() === hit.id ? null : hit.id);
  }

  fields(hit: LogHit): [string, string][] {
    const out: [string, string][] = [];
    const walk = (obj: Record<string, unknown>, prefix: string) => {
      for (const [k, v] of Object.entries(obj)) {
        const key = prefix ? `${prefix}.${k}` : k;
        if (HIDDEN_DETAIL_FIELDS.has(key)) continue;
        if (v && typeof v === 'object' && !Array.isArray(v)) walk(v as Record<string, unknown>, key);
        else out.push([key, Array.isArray(v) ? v.join(', ') : String(v)]);
      }
    };
    walk(hit.source, '');
    return out.sort((a, b) => a[0].localeCompare(b[0]));
  }

  showContext(hit: LogHit) {
    this.api.event(hit.id).subscribe({ next: r => this.context.set(r.context), error: e => this.notify.error(e) });
  }

  filterTrace(traceId: string) {
    this.fieldFilters.set([{ field: 'trace_id', op: 'eq', value: traceId }]);
    this.range = '7d';
    this.search();
  }

  saveSearch() {
    const name = prompt('Name for this saved search');
    if (!name) return;
    this.api.savedSearches.create({
      name, description: '', provider: this.provider, query: this.q, query_mode: this.mode,
      filters: { ...(this.levels.length ? { level: this.levels } : {}), ...this.filters() } as Record<string, string[]>,
      field_filters: this.fieldFilters(), time_range: this.range, is_shared: true,
    }).subscribe({
      next: s => { this.saved.update(list => [...list, s]); this.notify.ok('Search saved'); },
      error: e => this.notify.error(e),
    });
  }

  applySaved(s: SavedSearch) {
    this.q = s.query;
    this.mode = s.query_mode as 'simple' | 'lucene';
    this.provider = s.provider;
    this.range = s.time_range;
    const { level, ...rest } = s.filters as Record<string, string[]>;
    this.levels = level ?? [];
    this.filters.set(rest);
    this.fieldFilters.set(s.field_filters ?? []);
    this.search();
  }

  export(format: 'csv' | 'json') {
    this.api.exportLogs({ ...this.query(), size: undefined }, format).subscribe({
      next: blob => downloadBlob(blob, `loghub-logs.${format}`),
      error: e => this.notify.error(e),
    });
  }
}
