import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTabsModule } from '@angular/material/tabs';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { AlertEvent, NotificationChannel } from '../core/models';
import { Notify } from '../core/ui';
import { EmptyStateComponent, LevelBadgeComponent, PageHeaderComponent, StatusChipComponent } from '../shared/ui.components';

@Component({
  selector: 'lh-alerts',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink, MatButtonModule, MatButtonToggleModule, MatCardModule, MatFormFieldModule,
    MatIconModule, MatInputModule, MatSelectModule, MatSlideToggleModule, MatTabsModule, PageHeaderComponent,
    LevelBadgeComponent, StatusChipComponent, EmptyStateComponent],
  template: `
    <lh-page-header title="Alerts & Notifications" subtitle="Alert events from rules evaluated every 30 s by Celery">
      <a mat-stroked-button routerLink="/rules"><mat-icon>rule</mat-icon> Alert rules</a>
      <a mat-stroked-button routerLink="/detections"><mat-icon>shield</mat-icon> Detection rules</a>
    </lh-page-header>
    <mat-tab-group>
      <mat-tab label="Alert events">
        <div class="filter-row pad-top">
          <mat-button-toggle-group [(ngModel)]="status" (change)="load()" aria-label="Status filter">
            <mat-button-toggle value="">All</mat-button-toggle>
            <mat-button-toggle value="firing">Firing</mat-button-toggle>
            <mat-button-toggle value="acknowledged">Acknowledged</mat-button-toggle>
            <mat-button-toggle value="resolved">Resolved</mat-button-toggle>
          </mat-button-toggle-group>
        </div>
        <mat-card>
          <table class="data-table">
            <thead><tr><th>Severity</th><th>Alert</th><th>Status</th><th>Category</th><th class="num">Value</th>
              <th class="num">Evaluations</th><th>Started</th><th>Resolved</th><th></th></tr></thead>
            <tbody>
              @for (e of events(); track e.id) {
                <tr>
                  <td><lh-level [level]="e.severity" /></td>
                  <td><a [routerLink]="['/alerts/events', e.id]">{{ e.title }}</a><div class="muted small">{{ e.message }}</div></td>
                  <td><lh-status [status]="e.status" /></td><td>{{ e.category }}</td>
                  <td class="num">{{ e.value }}</td><td class="num">{{ e.occurrences }}</td>
                  <td class="muted">{{ e.started_at | date: 'short' }}</td>
                  <td class="muted">{{ e.resolved_at ? (e.resolved_at | date: 'short') : '—' }}</td>
                  <td class="actions">
                    @if (e.status === 'firing' && auth.hasRole('analyst')) {
                      <button mat-stroked-button (click)="ack(e)">Acknowledge</button>
                    }
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="9"><lh-empty icon="notifications_off" title="No alert events">Create a rule from a template to start alerting.</lh-empty></td></tr>
              }
            </tbody>
          </table>
        </mat-card>
      </mat-tab>

      <mat-tab label="Notification channels">
        <div class="pad-top">
          @if (auth.hasRole('admin')) {
            <mat-card class="form-card">
              <mat-card-header><mat-card-title>Add channel</mat-card-title></mat-card-header>
              <mat-card-content class="filter-row">
                <mat-form-field class="w-200"><mat-label>Name</mat-label><input matInput [(ngModel)]="draft.name" /></mat-form-field>
                <mat-form-field class="w-140"><mat-label>Type</mat-label>
                  <mat-select [(ngModel)]="draft.channel_type"><mat-option value="email">Email</mat-option><mat-option value="webhook">Webhook</mat-option></mat-select>
                </mat-form-field>
                @if (draft.channel_type === 'email') {
                  <mat-form-field class="grow"><mat-label>Recipients (comma-separated)</mat-label><input matInput [(ngModel)]="recipients" /></mat-form-field>
                } @else {
                  <mat-form-field class="grow"><mat-label>Webhook URL</mat-label><input matInput [(ngModel)]="webhookUrl" /></mat-form-field>
                  <mat-form-field class="w-200"><mat-label>Signing secret (optional)</mat-label><input matInput type="password" [(ngModel)]="draft.secret" autocomplete="new-password" /></mat-form-field>
                }
                <mat-slide-toggle [(ngModel)]="draft.send_resolved">Send resolved</mat-slide-toggle>
                <button mat-flat-button color="primary" (click)="addChannel()" [disabled]="!draft.name">Add</button>
              </mat-card-content>
            </mat-card>
          }
          <mat-card>
            <table class="data-table">
              <thead><tr><th>Name</th><th>Type</th><th>Target</th><th>Enabled</th><th>Resolved notices</th><th></th></tr></thead>
              <tbody>
                @for (c of channels(); track c.id) {
                  <tr><td>{{ c.name }}</td><td>{{ c.channel_type }}</td>
                    <td class="mono small">{{ c.channel_type === 'email' ? c.config['recipients']?.join(', ') : c.config['url'] }}
                      @if (c.has_secret) { <span class="muted">(signed)</span> }</td>
                    <td><lh-status [status]="c.enabled ? 'healthy' : 'disabled'" [label]="c.enabled ? 'enabled' : 'disabled'" /></td>
                    <td>{{ c.send_resolved ? 'yes' : 'no' }}</td>
                    <td class="actions">
                      @if (auth.hasRole('admin')) {
                        <button mat-stroked-button (click)="test(c)"><mat-icon>send</mat-icon> Test</button>
                        <button mat-icon-button (click)="removeChannel(c)" aria-label="Delete channel"><mat-icon>delete</mat-icon></button>
                      }
                    </td></tr>
                } @empty { <tr><td colspan="6" class="muted">No channels configured.</td></tr> }
              </tbody>
            </table>
          </mat-card>
          <p class="muted small">In development, email goes to the bundled Mailpit inbox (http://localhost:8025). Configure EMAIL_* in .env for a real SMTP relay.</p>
        </div>
      </mat-tab>
    </mat-tab-group>
  `,
})
export class AlertsComponent {
  private api = inject(ApiService);
  private notify = inject(Notify);
  auth = inject(AuthService);
  events = signal<AlertEvent[]>([]);
  channels = signal<NotificationChannel[]>([]);
  status = '';
  draft: NotificationChannel = { name: '', channel_type: 'email', config: {}, enabled: true, send_resolved: true, secret: '' };
  recipients = '';
  webhookUrl = '';

  constructor() {
    this.load();
    this.loadChannels();
  }

  load() {
    this.api.events.list(this.status ? { status: this.status } : {}).subscribe(r => this.events.set(r.results));
  }
  loadChannels() { this.api.channels.list().subscribe(r => this.channels.set(r.results)); }

  ack(e: AlertEvent) {
    const note = prompt('Acknowledgement note (optional)') ?? '';
    this.api.events.action(e.id, 'acknowledge', { note }).subscribe({ next: () => this.load(), error: err => this.notify.error(err) });
  }

  addChannel() {
    const config = this.draft.channel_type === 'email'
      ? { recipients: this.recipients.split(',').map(r => r.trim()).filter(Boolean) }
      : { url: this.webhookUrl.trim() };
    this.api.channels.create({ ...this.draft, config }).subscribe({
      next: () => {
        this.notify.ok('Channel added');
        this.draft = { name: '', channel_type: 'email', config: {}, enabled: true, send_resolved: true, secret: '' };
        this.recipients = this.webhookUrl = '';
        this.loadChannels();
      },
      error: e => this.notify.error(e),
    });
  }

  test(c: NotificationChannel) {
    this.api.channels.action<{ status: string; error: string }>(c.id!, 'test').subscribe({
      next: d => d.status === 'failed' ? this.notify.error(new Error(d.error)) : this.notify.ok(`Test notification ${d.status}`),
      error: e => this.notify.error(e),
    });
  }

  removeChannel(c: NotificationChannel) {
    if (!confirm(`Delete channel "${c.name}"?`)) return;
    this.api.channels.remove(c.id!).subscribe({ next: () => this.loadChannels(), error: e => this.notify.error(e) });
  }
}
