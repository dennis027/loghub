import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { ThemeService } from '../core/theme.service';
import { Notify, TIME_RANGES } from '../core/ui';
import { PageHeaderComponent } from '../shared/ui.components';

@Component({
  selector: 'lh-settings',
  standalone: true,
  imports: [FormsModule, MatButtonModule, MatCardModule, MatFormFieldModule, MatInputModule, MatSelectModule, PageHeaderComponent],
  template: `
    <lh-page-header title="System Settings" />
    <section class="grid-2">
      <mat-card><mat-card-header><mat-card-title>My preferences</mat-card-title></mat-card-header>
        <mat-card-content class="form-grid single">
          <mat-form-field><mat-label>Appearance</mat-label>
            <mat-select [value]="theme.mode()" (selectionChange)="theme.mode.set($event.value)">
              <mat-option value="dark">Dark</mat-option><mat-option value="light">Light</mat-option>
            </mat-select><mat-hint>Saved in this browser; applies immediately.</mat-hint></mat-form-field>
          <mat-form-field><mat-label>Default time range</mat-label>
            <mat-select [(ngModel)]="prefs.default_time_range">@for (r of ranges; track r.value) { <mat-option [value]="r.value">{{ r.label }}</mat-option> }</mat-select></mat-form-field>
          <mat-form-field><mat-label>Live log buffer (events)</mat-label><input matInput type="number" min="50" max="5000" [(ngModel)]="prefs.live_event_limit" /></mat-form-field>
          <button mat-flat-button color="primary" (click)="savePrefs()">Save preferences</button>
        </mat-card-content></mat-card>

      <mat-card><mat-card-header><mat-card-title>Change password</mat-card-title></mat-card-header>
        <mat-card-content class="form-grid single">
          <mat-form-field><mat-label>Current password</mat-label><input matInput type="password" [(ngModel)]="pw.current" autocomplete="current-password" /></mat-form-field>
          <mat-form-field><mat-label>New password</mat-label><input matInput type="password" [(ngModel)]="pw.next" autocomplete="new-password" /></mat-form-field>
          <button mat-flat-button color="primary" (click)="changePassword()" [disabled]="!pw.current || !pw.next">Change password</button>
        </mat-card-content></mat-card>

      <mat-card class="span-2"><mat-card-header><mat-card-title>Organization</mat-card-title>
          <mat-card-subtitle>Data stream: logs-loghub-{{ org()?.slug }}</mat-card-subtitle></mat-card-header>
        <mat-card-content class="form-grid">
          @if (org(); as o) {
            <mat-form-field><mat-label>Name</mat-label><input matInput [(ngModel)]="o.name" [disabled]="!isAdmin" /></mat-form-field>
            <mat-form-field><mat-label>Description</mat-label><input matInput [(ngModel)]="o.description" [disabled]="!isAdmin" /></mat-form-field>
            <mat-form-field class="span-2"><mat-label>Additional masked fields (comma-separated)</mat-label>
              <input matInput class="mono" [(ngModel)]="masked" [disabled]="!isAdmin" placeholder="customer.email, card_last4" />
              <mat-hint>Replaced with [MASKED] in search results and exports for everyone. Passwords, tokens and keys are always redacted at ingest.</mat-hint></mat-form-field>
            @if (isAdmin) { <button mat-flat-button color="primary" (click)="saveOrg()">Save organization</button> }
          }
        </mat-card-content></mat-card>
    </section>
  `,
})
export class SettingsComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);
  theme = inject(ThemeService);
  private notify = inject(Notify);
  ranges = TIME_RANGES;
  isAdmin = this.auth.hasRole('admin');
  prefs = { ...this.auth.user()!.preferences };
  pw = { current: '', next: '' };
  org = signal<any>(null);
  masked = '';

  constructor() {
    this.api.organization().subscribe(o => { this.org.set(o); this.masked = (o.masked_fields ?? []).join(', '); });
  }

  savePrefs() {
    this.api.updatePreferences(this.prefs).subscribe({
      next: () => { this.auth.loadUser().subscribe(); this.notify.ok('Preferences saved'); }, error: e => this.notify.error(e),
    });
  }
  changePassword() {
    this.api.changePassword(this.pw.current, this.pw.next).subscribe({
      next: () => { this.pw = { current: '', next: '' }; this.notify.ok('Password changed'); }, error: e => this.notify.error(e),
    });
  }
  saveOrg() {
    const o = this.org();
    const masked_fields = this.masked.split(',').map(s => s.trim()).filter(Boolean);
    this.api.updateOrganization({ name: o.name, description: o.description, masked_fields }).subscribe({
      next: r => { this.org.set(r); this.notify.ok('Organization saved'); }, error: e => this.notify.error(e),
    });
  }
}
