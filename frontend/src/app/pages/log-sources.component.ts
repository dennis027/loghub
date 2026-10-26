import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Collector, InstructionStep, LogSource } from '../core/models';
import { Notify } from '../core/ui';
import { CopyButtonComponent, EmptyStateComponent, PageHeaderComponent, StatusChipComponent } from '../shared/ui.components';

const TYPES = [
  ['docker', 'Docker container'], ['linux', 'Linux server'], ['nginx', 'Nginx'], ['apache', 'Apache'],
  ['django', 'Django application'], ['node', 'Node.js application'], ['go', 'Go application'],
  ['postgres', 'PostgreSQL'], ['mysql', 'MySQL'], ['kubernetes', 'Kubernetes workload'], ['syslog', 'Syslog device'],
  ['custom', 'Custom HTTP application'],
];

@Component({
  selector: 'lh-log-sources',
  standalone: true,
  imports: [DatePipe, ReactiveFormsModule, RouterLink, MatButtonModule, MatCardModule, MatFormFieldModule, MatIconModule,
    MatInputModule, MatSelectModule, MatSlideToggleModule, MatTabsModule, MatTooltipModule, PageHeaderComponent,
    StatusChipComponent, CopyButtonComponent, EmptyStateComponent],
  template: `
    <lh-page-header title="Log Sources" subtitle="Registered systems; status is computed from what has actually been indexed">
      @if (auth.hasRole('editor')) {
        <button mat-flat-button color="primary" (click)="openForm()"><mat-icon>add</mat-icon> Register source</button>
      }
    </lh-page-header>

    @if (formOpen()) {
      <mat-card class="form-card">
        <mat-card-header><mat-card-title>{{ editingId() ? 'Edit source' : 'Register a log source' }}</mat-card-title></mat-card-header>
        <mat-card-content>
          <form [formGroup]="form" (ngSubmit)="save()" class="form-grid">
            <mat-form-field><mat-label>Name</mat-label><input matInput formControlName="name" required />
              <mat-hint>Used as the service name for attribution</mat-hint></mat-form-field>
            <mat-form-field><mat-label>Type</mat-label>
              <mat-select formControlName="source_type">@for (t of types; track t[0]) { <mat-option [value]="t[0]">{{ t[1] }}</mat-option> }</mat-select></mat-form-field>
            <mat-form-field><mat-label>Environment</mat-label><input matInput formControlName="environment" /></mat-form-field>
            <mat-form-field><mat-label>Hostname</mat-label><input matInput formControlName="hostname" /></mat-form-field>
            <mat-form-field><mat-label>Endpoint (optional)</mat-label><input matInput formControlName="endpoint" /></mat-form-field>
            <mat-form-field><mat-label>Routing</mat-label>
              <mat-select formControlName="log_route">
                <mat-option value="elk">Elasticsearch (via Logstash)</mat-option>
                <mat-option value="graylog">Graylog only</mat-option>
                <mat-option value="both">Both (duplicates storage)</mat-option>
              </mat-select></mat-form-field>
            <mat-form-field><mat-label>Attribute events by</mat-label>
              <mat-select formControlName="match_field">
                <mat-option value="source_id">Ingest token (HTTP API)</mat-option>
                <mat-option value="service">Service name</mat-option>
                <mat-option value="hostname">Hostname</mat-option>
                <mat-option value="container">Container name</mat-option>
              </mat-select></mat-form-field>
            <mat-form-field><mat-label>Match value</mat-label><input matInput formControlName="match_value" placeholder="defaults to the name" /></mat-form-field>
            <mat-form-field><mat-label>Stale after (minutes)</mat-label><input matInput type="number" formControlName="stale_after_minutes" /></mat-form-field>
            <mat-form-field class="span-2"><mat-label>Description</mat-label><input matInput formControlName="description" /></mat-form-field>
            <mat-slide-toggle formControlName="enabled">Enabled</mat-slide-toggle>
            <div class="form-actions">
              <button mat-button type="button" (click)="formOpen.set(false)">Cancel</button>
              <button mat-flat-button color="primary" [disabled]="form.invalid">Save</button>
            </div>
          </form>
        </mat-card-content>
      </mat-card>
    }

    @if (revealed(); as r) {
      <div class="banner secret" role="alert">
        <mat-icon>key</mat-icon>
        <div><strong>Ingest token for {{ r.name }}</strong> — shown once, store it in your secret manager now.
          <div class="token-row"><code>{{ r.token }}</code><lh-copy [text]="r.token" label="Copy token" /></div></div>
        <button mat-button (click)="revealed.set(null)">I've stored it</button>
      </div>
    }

    <mat-card>
      <table class="data-table">
        <thead><tr><th>Name</th><th>Type</th><th>Environment</th><th>Status</th><th>Last seen</th><th class="num">Events 24h</th>
          <th>Route</th><th>Attribution</th><th>Owner</th><th></th></tr></thead>
        <tbody>
          @for (s of sources(); track s.id) {
            <tr [class.selected]="selected()?.id === s.id">
              <td><button type="button" class="link-button" (click)="select(s)">{{ s.name }}</button></td>
              <td>{{ typeLabel(s.source_type) }}</td><td>{{ s.environment }}</td>
              <td><lh-status [status]="s.status" /></td>
              <td class="muted">{{ s.last_seen ? (s.last_seen | date: 'short') : 'never' }}</td>
              <td class="num">{{ s.events_24h }}</td><td>{{ s.log_route }}</td>
              <td class="mono small">{{ s.match_field }}={{ s.effective_match_value }}</td>
              <td>{{ s.owner_username }}</td>
              <td class="actions">
                <a mat-icon-button [routerLink]="['/explore']" [queryParams]="exploreParams(s)" matTooltip="View logs" aria-label="View logs"><mat-icon>manage_search</mat-icon></a>
                @if (auth.hasRole('editor')) {
                  <button mat-icon-button (click)="openForm(s)" matTooltip="Edit" aria-label="Edit"><mat-icon>edit</mat-icon></button>
                  <button mat-icon-button (click)="remove(s)" matTooltip="Delete" aria-label="Delete"><mat-icon>delete</mat-icon></button>
                }
              </td>
            </tr>
          } @empty {
            <tr><td colspan="10"><lh-empty icon="input" title="No sources registered">Register a source to get setup instructions and status tracking.</lh-empty></td></tr>
          }
        </tbody>
      </table>
    </mat-card>

    @if (selected(); as s) {
      <mat-card class="detail-card">
        <mat-card-header>
          <mat-card-title>Set up {{ s.name }}</mat-card-title>
          <mat-card-subtitle>{{ s.source_key }} · token {{ s.has_token ? s.token_prefix + '…' : 'not issued' }}</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          @if (auth.hasRole('editor')) {
            <div class="detail-actions">
              <button mat-stroked-button (click)="rotate(s)"><mat-icon>autorenew</mat-icon> {{ s.has_token ? 'Rotate' : 'Issue' }} ingest token</button>
              @if (s.has_token) { <button mat-button color="warn" (click)="revoke(s)">Revoke token</button> }
            </div>
          }
          <mat-tab-group>
            @for (step of steps(); track step.title) {
              <mat-tab [label]="step.title">
                <p>{{ step.description }}</p>
                @if (step.filename) { <div class="muted small mono">{{ step.filename }}</div> }
                <div class="code-block"><lh-copy [text]="step.content" /><pre>{{ step.content }}</pre></div>
              </mat-tab>
            }
          </mat-tab-group>
        </mat-card-content>
      </mat-card>
    }

    <h3 class="folder-title">Collectors</h3>
    <mat-card>
      <table class="data-table">
        <thead><tr><th>Name</th><th>Type</th><th>Endpoint</th><th>Status</th><th>Last heartbeat</th></tr></thead>
        <tbody>
          @for (c of collectors(); track c.id) {
            <tr><td>{{ c.name }}</td><td>{{ c.collector_type }}</td><td class="mono small">{{ c.endpoint }}</td>
              <td><lh-status [status]="c.status" [label]="c.status + (c.status_message ? ' · ' + c.status_message : '')" /></td>
              <td class="muted">{{ c.last_heartbeat ? (c.last_heartbeat | date: 'medium') : '—' }}</td></tr>
          }
        </tbody>
      </table>
    </mat-card>
  `,
})
export class LogSourcesComponent {
  private api = inject(ApiService);
  private fb = inject(FormBuilder);
  private notify = inject(Notify);
  auth = inject(AuthService);
  types = TYPES;
  sources = signal<LogSource[]>([]);
  collectors = signal<Collector[]>([]);
  selected = signal<LogSource | null>(null);
  steps = signal<InstructionStep[]>([]);
  formOpen = signal(false);
  editingId = signal<number | null>(null);
  revealed = signal<{ name: string; token: string } | null>(null);

  form = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(255)]],
    source_type: ['custom'], environment: ['production'], hostname: [''], endpoint: [''], description: [''],
    log_route: ['elk'], match_field: ['source_id'], match_value: [''], stale_after_minutes: [15], enabled: [true],
  });

  constructor() {
    this.load();
    this.api.collectors.list().subscribe(r => this.collectors.set(r.results));
    this.form.controls.source_type.valueChanges.subscribe(t => {
      if (!this.editingId()) this.form.controls.match_field.setValue(t === 'custom' ? 'source_id' : 'service');
    });
  }

  load() { this.api.sources.list({ page_size: 200 }).subscribe(r => this.sources.set(r.results)); }
  typeLabel(t: string) { return TYPES.find(x => x[0] === t)?.[1] ?? t; }
  exploreParams(s: LogSource) { return { [s.match_field]: s.effective_match_value, range: '24h' }; }

  openForm(s?: LogSource) {
    this.editingId.set(s?.id ?? null);
    this.form.reset();
    if (s) this.form.patchValue(s as never);
    this.formOpen.set(true);
  }

  save() {
    const body = this.form.getRawValue();
    const id = this.editingId();
    const req = id ? this.api.sources.update(id, body as never) : this.api.sources.create(body as never);
    req.subscribe({
      next: s => { this.formOpen.set(false); this.notify.ok(id ? 'Source updated' : 'Source registered'); this.load(); this.select(s); },
      error: e => this.notify.error(e),
    });
  }

  select(s: LogSource) {
    this.selected.set(s);
    this.api.sourceInstructions(s.id).subscribe(r => this.steps.set(r.steps));
  }

  rotate(s: LogSource) {
    if (s.has_token && !confirm('Rotating invalidates the current token immediately. Continue?')) return;
    this.api.sources.action<{ token: string }>(s.id, 'rotate-token').subscribe({
      next: r => { this.revealed.set({ name: s.name, token: r.token }); this.load(); this.selected.set({ ...s, has_token: true, token_prefix: r.token.slice(0, 10) }); },
      error: e => this.notify.error(e),
    });
  }

  revoke(s: LogSource) {
    if (!confirm('Revoke the ingest token? Clients using it will be rejected.')) return;
    this.api.sources.action(s.id, 'revoke-token').subscribe({ next: () => { this.load(); this.selected.set({ ...s, has_token: false }); } });
  }

  remove(s: LogSource) {
    if (!confirm(`Delete source "${s.name}"? Indexed logs are kept.`)) return;
    this.api.sources.remove(s.id).subscribe({ next: () => { this.load(); this.selected.set(null); }, error: e => this.notify.error(e) });
  }
}
