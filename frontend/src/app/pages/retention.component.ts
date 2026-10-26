import { DatePipe, JsonPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { RetentionPolicy } from '../core/models';
import { Notify, formatBytes } from '../core/ui';
import { PageHeaderComponent, StatusChipComponent } from '../shared/ui.components';

@Component({
  selector: 'lh-retention',
  standalone: true,
  imports: [DatePipe, JsonPipe, FormsModule, MatButtonModule, MatCardModule, MatFormFieldModule, MatInputModule,
    PageHeaderComponent, StatusChipComponent],
  template: `
    <lh-page-header title="Retention Policies" subtitle="Index lifecycle for log data. Synced to the Elasticsearch ILM policy loghub-logs." />
    @for (p of policies(); track p.id) {
      <mat-card class="form-card">
        <mat-card-header><mat-card-title>{{ p.name }}</mat-card-title>
          <mat-card-subtitle><lh-status [status]="p.sync_status" /> {{ p.sync_message }}
            @if (p.last_synced_at) { · {{ p.last_synced_at | date: 'medium' }} } @if (p.updated_by) { · by {{ p.updated_by }} }</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <div class="filter-row">
            <mat-form-field class="w-200"><mat-label>Roll over after (days)</mat-label>
              <input matInput type="number" min="1" max="30" [(ngModel)]="p.rollover_days" [disabled]="!canEdit" /></mat-form-field>
            <mat-form-field class="w-200"><mat-label>Delete after (days)</mat-label>
              <input matInput type="number" min="1" max="3650" [(ngModel)]="p.delete_after_days" [disabled]="!canEdit" /></mat-form-field>
            @if (canEdit) { <button mat-flat-button color="primary" (click)="save(p)">Save &amp; sync</button> }
          </div>
          <p class="muted small">A backing index is deleted {{ p.delete_after_days }} days after it rolls over, so the oldest
            searchable event is up to {{ p.rollover_days + p.delete_after_days }} days old. This policy is cluster-wide (every organization's
            data stream uses it) and only platform administrators can change it. Graylog retention is configured per index set in Graylog.</p>
          @if (live(); as l) {
            <h4>Current state in Elasticsearch</h4>
            <p>Organization data stream: {{ l.storage?.data_stream?.name ?? 'not created yet' }} ·
              {{ bytes(l.storage?.data_stream?.store_size_bytes) }} in {{ l.storage?.data_stream?.backing_indices ?? 0 }} backing indices ·
              cluster disk {{ l.storage?.disk?.used_percent ?? '—' }}% used</p>
            <details><summary>ILM policy JSON</summary><pre class="mono">{{ l.ilm?.policy | json }}</pre></details>
          }
        </mat-card-content>
      </mat-card>
    }
  `,
})
export class RetentionComponent {
  private api = inject(ApiService);
  private notify = inject(Notify);
  private auth = inject(AuthService);
  canEdit = this.auth.hasRole('admin') && !!this.auth.user()?.is_staff;
  policies = signal<RetentionPolicy[]>([]);
  live = signal<any>(null);
  bytes = formatBytes;

  constructor() { this.load(); }

  load() {
    this.api.retention().subscribe(list => {
      this.policies.set(list);
      if (list[0]) this.api.retentionLive(list[0].id).subscribe(l => this.live.set(l));
    });
  }

  save(p: RetentionPolicy) {
    this.api.updateRetention(p.id, { rollover_days: p.rollover_days, delete_after_days: p.delete_after_days }).subscribe({
      next: r => { this.notify.ok(r.sync_status === 'synced' ? 'Policy synced to Elasticsearch' : `Saved, sync failed: ${r.sync_message}`); this.load(); },
      error: e => this.notify.error(e),
    });
  }
}
