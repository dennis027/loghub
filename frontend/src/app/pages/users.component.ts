import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTabsModule } from '@angular/material/tabs';
import { ApiService } from '../core/api.service';
import { Role, Team, User } from '../core/models';
import { Notify } from '../core/ui';
import { PageHeaderComponent } from '../shared/ui.components';

const ROLES: { value: Role; label: string; help: string }[] = [
  { value: 'viewer', label: 'Viewer', help: 'Read dashboards, search logs (personal fields masked)' },
  { value: 'analyst', label: 'Analyst', help: '+ export, saved searches, acknowledge alerts, see personal fields' },
  { value: 'editor', label: 'Editor', help: '+ manage sources, rules, dashboards' },
  { value: 'admin', label: 'Administrator', help: '+ users, teams, channels, audit log' },
];

function blankUser(): User {
  return { username: '', email: '', first_name: '', last_name: '', role: 'viewer', is_active: true, teams: [], password: '' };
}

@Component({
  selector: 'lh-users',
  standalone: true,
  imports: [DatePipe, FormsModule, MatButtonModule, MatCardModule, MatFormFieldModule, MatIconModule, MatInputModule,
    MatSelectModule, MatSlideToggleModule, MatTabsModule, PageHeaderComponent],
  template: `
    <lh-page-header title="Users & Roles" subtitle="Members of your organization and what they can do" />
    <mat-tab-group>
      <mat-tab label="Users">
        <div class="pad-top">
          @if (draft(); as u) {
            <mat-card class="form-card"><mat-card-content>
              <div class="form-grid">
                <mat-form-field><mat-label>Username</mat-label><input matInput [(ngModel)]="u.username" [disabled]="!!u.id" /></mat-form-field>
                <mat-form-field><mat-label>Email</mat-label><input matInput type="email" [(ngModel)]="u.email" /></mat-form-field>
                <mat-form-field><mat-label>First name</mat-label><input matInput [(ngModel)]="u.first_name" /></mat-form-field>
                <mat-form-field><mat-label>Last name</mat-label><input matInput [(ngModel)]="u.last_name" /></mat-form-field>
                <mat-form-field><mat-label>Role</mat-label>
                  <mat-select [(ngModel)]="u.role">@for (r of roles; track r.value) { <mat-option [value]="r.value">{{ r.label }}</mat-option> }</mat-select>
                  <mat-hint>{{ roleHelp(u.role) }}</mat-hint></mat-form-field>
                <mat-form-field><mat-label>Teams</mat-label>
                  <mat-select multiple [(ngModel)]="u.teams">@for (t of teams(); track t.id) { <mat-option [value]="t.id">{{ t.name }}</mat-option> }</mat-select></mat-form-field>
                <mat-form-field><mat-label>{{ u.id ? 'New password (optional)' : 'Password' }}</mat-label>
                  <input matInput type="password" [(ngModel)]="u.password" autocomplete="new-password" />
                  <mat-hint>At least 10 characters, not common or numeric-only</mat-hint></mat-form-field>
                <mat-slide-toggle [(ngModel)]="u.is_active">Active</mat-slide-toggle>
              </div>
              <div class="form-actions"><button mat-button (click)="draft.set(null)">Cancel</button>
                <button mat-flat-button color="primary" (click)="saveUser(u)">Save</button></div>
            </mat-card-content></mat-card>
          } @else {
            <button mat-flat-button color="primary" (click)="draft.set(blank())"><mat-icon>person_add</mat-icon> Add user</button>
          }
          <mat-card><table class="data-table">
            <thead><tr><th>User</th><th>Email</th><th>Role</th><th>Teams</th><th>Status</th><th>Last login</th><th></th></tr></thead>
            <tbody>
              @for (u of users(); track u.id) {
                <tr><td>{{ u.username }} <span class="muted">{{ u.first_name }} {{ u.last_name }}</span></td><td>{{ u.email }}</td>
                  <td><span class="pill">{{ u.role }}</span></td><td>{{ teamNames(u.teams) }}</td>
                  <td>{{ u.is_active ? 'active' : 'disabled' }}</td>
                  <td class="muted">{{ u.last_login ? (u.last_login | date: 'short') : 'never' }}</td>
                  <td class="actions"><button mat-icon-button (click)="editUser(u)" aria-label="Edit user"><mat-icon>edit</mat-icon></button></td></tr>
              }
            </tbody>
          </table></mat-card>
          <mat-card class="pad-top"><mat-card-header><mat-card-title>Roles</mat-card-title></mat-card-header>
            <mat-card-content><table class="data-table"><tbody>
              @for (r of roles; track r.value) { <tr><td><strong>{{ r.label }}</strong></td><td>{{ r.help }}</td></tr> }
            </tbody></table></mat-card-content></mat-card>
        </div>
      </mat-tab>
      <mat-tab label="Teams">
        <div class="pad-top">
          <div class="filter-row">
            <mat-form-field class="w-200"><mat-label>New team</mat-label><input matInput [(ngModel)]="teamName" /></mat-form-field>
            <button mat-flat-button color="primary" (click)="addTeam()" [disabled]="!teamName">Add team</button>
          </div>
          <mat-card><table class="data-table"><thead><tr><th>Team</th><th class="num">Members</th><th></th></tr></thead><tbody>
            @for (t of teams(); track t.id) {
              <tr><td>{{ t.name }}</td><td class="num">{{ t.member_count }}</td>
                <td class="actions"><button mat-icon-button (click)="removeTeam(t)" aria-label="Delete team"><mat-icon>delete</mat-icon></button></td></tr>
            }
          </tbody></table></mat-card>
        </div>
      </mat-tab>
    </mat-tab-group>
  `,
})
export class UsersComponent {
  private api = inject(ApiService);
  private notify = inject(Notify);
  roles = ROLES;
  users = signal<User[]>([]);
  teams = signal<Team[]>([]);
  draft = signal<User | null>(null);
  teamName = '';
  blank = blankUser;

  constructor() { this.load(); }
  load() {
    this.api.users.list({ page_size: 200 }).subscribe(r => this.users.set(r.results));
    this.api.teams.list({ page_size: 200 }).subscribe(r => this.teams.set(r.results));
  }
  editUser(u: User) { this.draft.set({ ...u, password: '' }); }
  roleHelp(role: Role) { return ROLES.find(r => r.value === role)?.help; }
  teamNames(ids: number[]) { return this.teams().filter(t => ids.includes(t.id!)).map(t => t.name).join(', '); }

  saveUser(u: User) {
    const { id, last_login, ...body } = u;
    if (!body.password) delete body.password;
    (id ? this.api.users.update(id, body) : this.api.users.create(body)).subscribe({
      next: () => { this.draft.set(null); this.notify.ok('User saved'); this.load(); }, error: e => this.notify.error(e),
    });
  }
  addTeam() {
    this.api.teams.create({ name: this.teamName, description: '' }).subscribe({
      next: () => { this.teamName = ''; this.load(); }, error: e => this.notify.error(e),
    });
  }
  removeTeam(t: Team) {
    if (!confirm(`Delete team "${t.name}"?`)) return;
    this.api.teams.remove(t.id!).subscribe({ next: () => this.load(), error: e => this.notify.error(e) });
  }
}
