import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';
import { Notify, TIME_RANGES } from '../core/ui';
import { EmptyStateComponent, PageHeaderComponent } from '../shared/ui.components';

@Component({
  selector: 'lh-services',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink, MatCardModule, MatSelectModule, MatProgressBarModule, PageHeaderComponent,
    EmptyStateComponent],
  template: `
    <lh-page-header title="Applications & Services" subtitle="Discovered from indexed logs (service field)">
      <mat-select class="range-select" [(ngModel)]="range" (selectionChange)="load()" aria-label="Time range">
        @for (r of ranges; track r.value) { <mat-option [value]="r.value">{{ r.label }}</mat-option> }
      </mat-select>
    </lh-page-header>
    @if (loading()) { <mat-progress-bar mode="indeterminate" /> }
    <mat-card>
      <table class="data-table">
        <thead><tr><th>Service</th><th class="num">Events</th><th class="num">Errors</th><th class="num">Warnings</th>
          <th>Error rate</th><th>Environments</th><th class="num">Hosts</th><th class="num">Containers</th><th>Last event</th><th>Registered</th></tr></thead>
        <tbody>
          @for (s of services(); track s.service) {
            <tr>
              <td><a [routerLink]="['/explore']" [queryParams]="{ service: s.service, range }">{{ s.service }}</a></td>
              <td class="num">{{ s.events.toLocaleString() }}</td>
              <td class="num">{{ s.errors }}</td><td class="num">{{ s.warnings }}</td>
              <td><div class="meter" [attr.aria-label]="s.error_rate + '% errors'">
                    <div class="meter-fill" [style.width.%]="min(s.error_rate, 100)" [class.hot]="s.error_rate >= 5"></div></div>
                  <span class="small">{{ s.error_rate }}%</span></td>
              <td>{{ s.environments.join(', ') }}</td>
              <td class="num">{{ s.hosts }}</td><td class="num">{{ s.containers }}</td>
              <td class="muted">{{ s.last_seen | date: 'short' }}</td>
              <td>@if (s.registered_source) { <a routerLink="/sources">{{ s.registered_source.name }}</a> } @else { <span class="muted">—</span> }</td>
            </tr>
          } @empty {
            <tr><td colspan="10"><lh-empty icon="apps" title="No services reported logs in this range" /></td></tr>
          }
        </tbody>
      </table>
    </mat-card>
  `,
})
export class ServicesComponent {
  private api = inject(ApiService);
  private notify = inject(Notify);
  ranges = TIME_RANGES;
  range = '24h';
  services = signal<any[]>([]);
  loading = signal(false);
  min = Math.min;

  constructor() { this.load(); }

  load() {
    this.loading.set(true);
    this.api.services(this.range).subscribe({
      next: r => { this.services.set(r.services); this.loading.set(false); },
      error: e => { this.loading.set(false); this.notify.error(e); },
    });
  }
}
