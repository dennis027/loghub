import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Integration } from '../core/models';
import { Notify } from '../core/ui';
import { PageHeaderComponent, StatusChipComponent } from '../shared/ui.components';

const ICONS: Record<string, string> = {
  elasticsearch: 'storage', logstash: 'filter_alt', 'fluent-bit': 'input', kibana: 'travel_explore', grafana: 'monitor_heart',
  graylog: 'hub', prometheus: 'speed',
};

@Component({
  selector: 'lh-integrations',
  standalone: true,
  imports: [DatePipe, MatButtonModule, MatCardModule, MatIconModule, MatSlideToggleModule, PageHeaderComponent, StatusChipComponent],
  template: `
    <lh-page-header title="Integrations" subtitle="Connected products. Credentials are held server-side and never sent to the browser." />
    <div class="card-grid wide">
      @for (i of items(); track i.provider) {
        <mat-card class="integration-card">
          <mat-card-header>
            <mat-icon mat-card-avatar>{{ icon(i.provider) }}</mat-icon>
            <mat-card-title>{{ i.name }}</mat-card-title>
            <mat-card-subtitle>{{ i.description }}</mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            <p><lh-status [status]="i.status" /> <span class="small">{{ i.status_message }}</span></p>
            <div class="muted small">
              @if (i.version) { v{{ i.version }} · } @if (i.latency_ms !== null) { {{ i.latency_ms }} ms · }
              checked {{ i.last_checked ? (i.last_checked | date: 'mediumTime') : 'never' }}
            </div>
            @if (i.details['dashboards']?.length) {
              <h4>Provisioned dashboards</h4>
              @for (d of i.details['dashboards']; track d.uid) { <div><a [href]="i.public_url + d.url" target="_blank" rel="noopener">{{ d.title }}</a></div> }
            }
            @if (i.provider === 'graylog' && graylog(); as g) {
              <h4>Inputs</h4>
              @for (inp of g.inputs; track inp.id) { <div class="small mono">{{ inp.title }} ({{ inp.type }} :{{ inp.port }})</div> }
              @empty { <div class="muted small">{{ g.message || 'none' }}</div> }
              <h4>Streams</h4>
              @for (s of g.streams; track s.id) { <div class="small">{{ s.title }} @if (s.disabled) {<span class="muted">(disabled)</span>}</div> }
            }
          </mat-card-content>
          <mat-card-actions>
            @if (i.public_url) { <a mat-button [href]="i.public_url" target="_blank" rel="noopener"><mat-icon>open_in_new</mat-icon> Open {{ i.name }}</a> }
            <button mat-button (click)="check(i)"><mat-icon>refresh</mat-icon> Check now</button>
            @if (isPlatformAdmin) {
              <mat-slide-toggle [checked]="i.enabled" (change)="toggle(i, $event.checked)">Enabled</mat-slide-toggle>
            }
          </mat-card-actions>
        </mat-card>
      }
    </div>
  `,
})
export class IntegrationsComponent {
  private api = inject(ApiService);
  private notify = inject(Notify);
  private auth = inject(AuthService);
  isPlatformAdmin = this.auth.hasRole('admin') && !!this.auth.user()?.is_staff;
  items = signal<Integration[]>([]);
  graylog = signal<any>(null);

  constructor() {
    this.api.integrations().subscribe(list => this.items.set(list));
    this.api.graylogOverview().subscribe(g => this.graylog.set(g));
  }
  icon(p: string) { return ICONS[p] ?? 'extension'; }
  check(i: Integration) {
    this.api.checkIntegration(i.provider).subscribe({
      next: u => this.items.update(list => list.map(x => (x.provider === u.provider ? u : x))), error: e => this.notify.error(e),
    });
  }
  toggle(i: Integration, enabled: boolean) {
    this.api.updateIntegration(i.provider, { enabled }).subscribe({
      next: u => this.items.update(list => list.map(x => (x.provider === u.provider ? u : x))), error: e => this.notify.error(e),
    });
  }
}
