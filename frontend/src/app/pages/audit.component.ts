import { DatePipe, JsonPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { ApiService } from '../core/api.service';
import { AuditEvent } from '../core/models';
import { PageHeaderComponent } from '../shared/ui.components';

@Component({
  selector: 'lh-audit',
  standalone: true,
  imports: [DatePipe, JsonPipe, FormsModule, MatButtonModule, MatCardModule, MatFormFieldModule, MatInputModule,
    MatPaginatorModule, PageHeaderComponent],
  template: `
    <lh-page-header title="Audit Logs" subtitle="Administrative actions in this organization (sensitive values redacted)">
      <mat-form-field class="w-200"><mat-label>Search</mat-label><input matInput [(ngModel)]="search" (keyup.enter)="load(1)" /></mat-form-field>
      <mat-form-field class="w-160"><mat-label>Action</mat-label><input matInput [(ngModel)]="action" (keyup.enter)="load(1)" placeholder="login, export…" /></mat-form-field>
    </lh-page-header>
    <mat-card>
      <table class="data-table">
        <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>Changes</th><th>IP</th></tr></thead>
        <tbody>
          @for (e of events(); track e.id) {
            <tr><td class="muted nowrap">{{ e.created_at | date: 'medium' }}</td><td>{{ e.actor_username }}</td>
              <td><span class="pill">{{ e.action }}</span></td>
              <td>{{ e.target_type }} {{ e.target_repr }}</td>
              <td class="mono small wrap">{{ hasChanges(e) ? (e.changes | json) : '' }}</td>
              <td class="mono small">{{ e.ip_address }}</td></tr>
          } @empty { <tr><td colspan="6" class="muted">No audit events.</td></tr> }
        </tbody>
      </table>
      <mat-paginator [length]="count()" [pageSize]="25" [hidePageSize]="true" (page)="page($event)" />
    </mat-card>
  `,
})
export class AuditComponent {
  private api = inject(ApiService);
  events = signal<AuditEvent[]>([]);
  count = signal(0);
  search = '';
  action = '';

  constructor() { this.load(1); }
  load(page: number) {
    const params: Record<string, string | number> = { page };
    if (this.search) params['search'] = this.search;
    if (this.action) params['action'] = this.action;
    this.api.audit.list(params).subscribe(r => { this.events.set(r.results); this.count.set(r.count); });
  }
  page(e: PageEvent) { this.load(e.pageIndex + 1); }
  hasChanges(e: AuditEvent) { return Object.keys(e.changes ?? {}).length > 0; }
}
