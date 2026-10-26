import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { AlertEvent } from '../core/models';
import { Notify } from '../core/ui';
import { JsonViewComponent, LevelBadgeComponent, PageHeaderComponent, StatusChipComponent } from '../shared/ui.components';

@Component({
  selector: 'lh-alert-event',
  standalone: true,
  imports: [DatePipe, RouterLink, MatButtonModule, MatCardModule, MatIconModule, PageHeaderComponent, LevelBadgeComponent,
    StatusChipComponent, JsonViewComponent],
  template: `
    @if (e(); as e) {
      <lh-page-header [title]="e.title" [subtitle]="e.message">
        <lh-level [level]="e.severity" /> <lh-status [status]="e.status" />
        @if (auth.hasRole('analyst') && e.status === 'firing') {
          <button mat-flat-button color="primary" (click)="act('acknowledge')">Acknowledge</button>
        }
        @if (auth.hasRole('analyst') && e.status !== 'resolved') {
          <button mat-stroked-button (click)="act('resolve')">Resolve</button>
        }
      </lh-page-header>
      <section class="grid-2">
        <mat-card><mat-card-header><mat-card-title>Timeline</mat-card-title></mat-card-header>
          <mat-card-content><table class="data-table"><tbody>
            <tr><td>Started</td><td>{{ e.started_at | date: 'medium' }}</td></tr>
            <tr><td>Last seen</td><td>{{ e.last_seen_at | date: 'medium' }}</td></tr>
            <tr><td>Evaluations while open</td><td>{{ e.occurrences }}</td></tr>
            <tr><td>Value / threshold</td><td>{{ e.value }} / {{ e.threshold }}</td></tr>
            <tr><td>Acknowledged</td><td>{{ e.acknowledged_by ? e.acknowledged_by + ' at ' + (e.acknowledged_at | date: 'medium') : '—' }}</td></tr>
            <tr><td>Resolved</td><td>{{ e.resolved_at ? (e.resolved_at | date: 'medium') : '—' }}</td></tr>
            @if (e.note) { <tr><td>Note</td><td>{{ e.note }}</td></tr> }
            <tr><td>Rule</td><td>@if (e.rule) { <a [routerLink]="e.category === 'security' ? '/detections' : '/rules'">{{ e.rule_name }}</a> } @else { {{ e.rule_name }} (deleted) }</td></tr>
          </tbody></table></mat-card-content></mat-card>
        <mat-card><mat-card-header><mat-card-title>Notifications</mat-card-title></mat-card-header>
          <mat-card-content><table class="data-table"><tbody>
            @for (d of e.deliveries; track $index) {
              <tr><td>{{ d.channel }}</td><td>{{ d.kind }}</td><td><lh-status [status]="d.status" /></td>
                <td class="muted small">{{ d.attempts }} attempt(s) {{ d.error }}</td><td class="muted">{{ d.sent_at | date: 'short' }}</td></tr>
            } @empty { <tr><td class="muted">No channels attached to this rule.</td></tr> }
          </tbody></table></mat-card-content></mat-card>
        <mat-card class="span-2"><mat-card-header><mat-card-title>Sample events at trigger time</mat-card-title></mat-card-header>
          <mat-card-content>
            @for (s of e.samples; track $index) {
              <div class="live-line"><span class="mono muted">{{ s.timestamp | date: 'medium' }}</span><lh-level [level]="s.level" />
                <span class="svc">{{ s.service }}</span><span class="mono msg">{{ s.message }}</span></div>
            } @empty { <div class="muted">No samples captured for this rule type.</div> }
            @if (hasContext(e)) { <lh-json [value]="e.context" /> }
          </mat-card-content></mat-card>
      </section>
    }
  `,
})
export class AlertEventComponent implements OnInit {
  id = input.required<string>();
  private api = inject(ApiService);
  private notify = inject(Notify);
  auth = inject(AuthService);
  e = signal<AlertEvent | null>(null);

  ngOnInit() { this.api.events.get(Number(this.id())).subscribe(e => this.e.set(e)); }
  hasContext(e: AlertEvent) { return Object.keys(e.context ?? {}).length > 0; }
  act(action: 'acknowledge' | 'resolve') {
    const note = prompt('Note (optional)') ?? '';
    this.api.events.action<AlertEvent>(this.e()!.id, action, { note }).subscribe({
      next: e => this.e.set(e), error: err => this.notify.error(err),
    });
  }
}
