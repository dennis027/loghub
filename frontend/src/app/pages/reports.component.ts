import { KeyValuePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { ApiService, downloadBlob } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Notify, TIME_RANGES } from '../core/ui';
import { EmptyStateComponent, PageHeaderComponent } from '../shared/ui.components';

@Component({
  selector: 'lh-reports',
  standalone: true,
  imports: [KeyValuePipe, FormsModule, MatButtonModule, MatCardModule, MatFormFieldModule, MatIconModule, MatProgressBarModule,
    MatSelectModule, PageHeaderComponent, EmptyStateComponent],
  template: `
    <lh-page-header title="Reports" subtitle="Generated on demand from indexed logs and alert history">
      <mat-form-field class="w-200"><mat-label>Report</mat-label>
        <mat-select [(ngModel)]="key" (selectionChange)="run()">@for (r of reports(); track r.key) { <mat-option [value]="r.key">{{ r.title }}</mat-option> }</mat-select>
      </mat-form-field>
      <mat-form-field class="w-180"><mat-label>Range</mat-label>
        <mat-select [(ngModel)]="range" (selectionChange)="run()">@for (r of ranges; track r.value) { <mat-option [value]="r.value">{{ r.label }}</mat-option> }</mat-select>
      </mat-form-field>
      @if (auth.hasRole('analyst')) {
        <button mat-stroked-button (click)="download('csv')" [disabled]="!report()"><mat-icon>download</mat-icon> CSV</button>
        <button mat-stroked-button (click)="download('pdf')" [disabled]="!report()"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
      }
    </lh-page-header>
    @if (loading()) { <mat-progress-bar mode="indeterminate" /> }
    @if (report(); as r) {
      <mat-card>
        <mat-card-header><mat-card-title>{{ r.title }}</mat-card-title>
          <mat-card-subtitle>@for (s of r.summary | keyvalue; track s.key) { {{ s.key }}: <strong>{{ s.value }}</strong> &nbsp; }</mat-card-subtitle></mat-card-header>
        <mat-card-content class="table-scroll">
          @if (r.rows.length) {
            <table class="data-table">
              <thead><tr>@for (c of r.columns; track c) { <th>{{ c }}</th> }</tr></thead>
              <tbody>@for (row of r.rows; track $index) { <tr>@for (v of row; track $index) { <td class="mono small wrap">{{ v }}</td> }</tr> }</tbody>
            </table>
          } @else { <lh-empty icon="summarize" title="No data in this range" /> }
        </mat-card-content>
      </mat-card>
    }
  `,
})
export class ReportsComponent {
  private api = inject(ApiService);
  private notify = inject(Notify);
  auth = inject(AuthService);
  reports = signal<{ key: string; title: string }[]>([]);
  ranges = TIME_RANGES.filter(r => r.value !== '15m');
  key = 'log-volume';
  range = '7d';
  report = signal<any>(null);
  loading = signal(false);

  constructor() {
    this.api.reports().subscribe(r => this.reports.set(r));
    this.run();
  }

  run() {
    this.loading.set(true);
    this.api.report(this.key, this.range).subscribe({
      next: r => { this.report.set(r); this.loading.set(false); },
      error: e => { this.loading.set(false); this.report.set(null); this.notify.error(e); },
    });
  }

  download(format: 'csv' | 'pdf') {
    this.api.reportFile(this.key, this.range, format).subscribe({
      next: b => downloadBlob(b, `loghub-${this.key}-${this.range}.${format}`), error: e => this.notify.error(e),
    });
  }
}
