import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../core/auth.service';
import { errorMessage } from '../core/ui';

@Component({
  selector: 'lh-login',
  standalone: true,
  imports: [ReactiveFormsModule, MatFormFieldModule, MatInputModule, MatButtonModule, MatIconModule, MatProgressBarModule],
  template: `
    <div class="login-page">
      <section class="login-hero" aria-hidden="true">
        <div class="brand big"><span class="brand-mark"><mat-icon>insights</mat-icon></span><span>LogHub</span></div>
        <div>
          <h1 class="hero-title">Every log, every service, one console.</h1>
          <p class="hero-text">Collect, search and alert on logs from containers, servers and applications, with
            Elasticsearch, Grafana, Kibana and Graylog behind a single access-controlled portal.</p>
          <div class="hero-points">
            <div class="hero-point"><mat-icon>bolt</mat-icon><div><strong>Search in seconds</strong>Full-text and Lucene queries, live tail, saved searches.</div></div>
            <div class="hero-point"><mat-icon>notifications_active</mat-icon><div><strong>Alert before users notice</strong>Thresholds, spikes, silent sources and security detections.</div></div>
            <div class="hero-point"><mat-icon>verified_user</mat-icon><div><strong>Secure by default</strong>Tenant isolation, role-based access, secret masking, full audit trail.</div></div>
          </div>
        </div>
        <div class="hero-stack"><span>Elasticsearch</span><span>Logstash</span><span>Fluent Bit</span><span>Kibana</span><span>Grafana</span><span>Graylog</span><span>Prometheus</span></div>
      </section>
      <section class="login-panel">
        <form class="login-card" [formGroup]="form" (ngSubmit)="submit()">
          <h2>Sign in</h2>
          <p class="subtitle">Use your LogHub account.</p>
          @if (expired) { <div class="banner warn">Your session expired. Please sign in again.</div> }
          @if (error()) { <div class="banner error" role="alert">{{ error() }}</div> }
          <mat-form-field>
            <mat-label>Username</mat-label>
            <input matInput formControlName="username" autocomplete="username" required />
          </mat-form-field>
          <mat-form-field>
            <mat-label>Password</mat-label>
            <input matInput [type]="showPw() ? 'text' : 'password'" formControlName="password" autocomplete="current-password" required />
            <button mat-icon-button matSuffix type="button" (click)="showPw.set(!showPw())" [attr.aria-label]="showPw() ? 'Hide password' : 'Show password'">
              <mat-icon>{{ showPw() ? 'visibility_off' : 'visibility' }}</mat-icon>
            </button>
          </mat-form-field>
          <button mat-flat-button color="primary" type="submit" [disabled]="form.invalid || busy()">Sign in</button>
          @if (busy()) { <mat-progress-bar mode="indeterminate" /> }
          <div class="login-foot">Access is logged. Contact your administrator if you need an account.</div>
        </form>
      </section>
    </div>
  `,
})
export class LoginComponent {
  private fb = inject(FormBuilder);
  private auth = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  form = this.fb.nonNullable.group({ username: ['', Validators.required], password: ['', Validators.required] });
  busy = signal(false);
  error = signal('');
  showPw = signal(false);
  expired = !!this.route.snapshot.queryParamMap.get('expired');

  submit() {
    if (this.form.invalid) return;
    this.busy.set(true);
    this.error.set('');
    const { username, password } = this.form.getRawValue();
    this.auth.login(username, password).subscribe({
      next: () => {
        const next = this.route.snapshot.queryParamMap.get('next');
        // Only follow same-app relative paths (no open redirects).
        this.router.navigateByUrl(next && next.startsWith('/') && !next.startsWith('//') ? next : '/overview');
      },
      error: err => {
        this.busy.set(false);
        this.error.set(errorMessage(err));
      },
    });
  }
}
