import { DatePipe } from '@angular/common';
import { AfterViewChecked, Component, ElementRef, OnDestroy, ViewChild, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { Subject, Subscription, debounceTime } from 'rxjs';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { LogHit } from '../core/models';
import { LiveTailService } from '../core/live-tail.service';
import { LEVELS } from '../core/ui';
import { LevelBadgeComponent, PageHeaderComponent, StatusChipComponent } from '../shared/ui.components';

@Component({
  selector: 'lh-live-logs',
  standalone: true,
  imports: [DatePipe, FormsModule, MatButtonModule, MatCardModule, MatFormFieldModule, MatIconModule, MatInputModule,
    MatSelectModule, MatSlideToggleModule, PageHeaderComponent, LevelBadgeComponent, StatusChipComponent],
  template: `
    <lh-page-header title="Live Logs" subtitle="Events as they are indexed (≈3 s behind real time, one server query every 2 s)">
      <lh-status [status]="statusKey()" [label]="statusLabel()" />
      @if (running()) {
        <button mat-flat-button color="warn" (click)="pause()"><mat-icon>pause</mat-icon> Pause</button>
      } @else {
        <button mat-flat-button color="primary" (click)="start()"><mat-icon>play_arrow</mat-icon> Start</button>
      }
      <button mat-stroked-button (click)="clear()"><mat-icon>delete_sweep</mat-icon> Clear</button>
    </lh-page-header>

    <mat-card class="query-card">
      <div class="filter-row">
        <mat-form-field class="grow">
          <mat-label>Filter (server-side, restarts stream)</mat-label>
          <input matInput [(ngModel)]="q" (ngModelChange)="filterChanged$.next()" placeholder="e.g. payment | timeout" />
        </mat-form-field>
        <mat-form-field class="w-160"><mat-label>Level</mat-label>
          <mat-select multiple [(ngModel)]="levels" (selectionChange)="restart()">
            @for (l of levelOptions; track l) { <mat-option [value]="l">{{ l }}</mat-option> }
          </mat-select>
        </mat-form-field>
        <mat-form-field class="w-200"><mat-label>Service</mat-label>
          <mat-select multiple [(ngModel)]="services" (selectionChange)="restart()" (openedChange)="$event && loadServices()">
            @for (s of serviceOptions(); track s) { <mat-option [value]="s">{{ s }}</mat-option> }
          </mat-select>
        </mat-form-field>
        <mat-form-field class="w-140"><mat-label>Keep last</mat-label>
          <mat-select [(ngModel)]="limit">
            @for (n of [200, 500, 1000, 2000, 5000]; track n) { <mat-option [value]="n">{{ n }} events</mat-option> }
          </mat-select>
        </mat-form-field>
        <mat-form-field class="w-200">
          <mat-label>Highlight (client-side)</mat-label>
          <input matInput [(ngModel)]="highlight" />
        </mat-form-field>
        <mat-slide-toggle [(ngModel)]="autoScroll">Auto-scroll</mat-slide-toggle>
      </div>
    </mat-card>

    @if (lastError()) { <div class="banner warn">{{ lastError() }}</div> }

    <div class="live-console" #console (scroll)="onScroll()" aria-live="off">
      @for (e of events(); track e.id) {
        <div class="live-line level-line-{{ e.level }}" [class.match]="matches(e)">
          <span class="mono muted">{{ e.timestamp | date: 'HH:mm:ss.SSS' }}</span>
          <lh-level [level]="e.level" />
          <span class="svc">{{ e.service }}</span>
          <span class="mono msg">{{ e.message }}</span>
        </div>
      } @empty {
        <div class="muted center pad">{{ running() ? 'Waiting for new events…' : 'Press Start to stream new events.' }}</div>
      }
    </div>
    <div class="muted small">{{ events().length }} events buffered · {{ received() }} received this session</div>
  `,
})
export class LiveLogsComponent implements OnDestroy, AfterViewChecked {
  @ViewChild('console') consoleEl?: ElementRef<HTMLDivElement>;
  private tail = inject(LiveTailService);
  private api = inject(ApiService);
  private auth = inject(AuthService);

  levelOptions = LEVELS;
  q = '';
  levels: string[] = [];
  services: string[] = [];
  serviceOptions = signal<string[]>([]);
  limit = this.auth.user()?.preferences.live_event_limit ?? 500;
  highlight = '';
  autoScroll = true;

  events = signal<LogHit[]>([]);
  received = signal(0);
  running = signal(false);
  status = signal<'connecting' | 'open' | 'reconnecting' | 'closed'>('closed');
  attempt = signal(0);
  lastError = signal('');
  statusKey = computed(() => ({ open: 'healthy', connecting: 'pending', reconnecting: 'degraded', closed: 'disabled' })[this.status()]);
  statusLabel = computed(() => ({
    open: 'Connected', connecting: 'Connecting…', reconnecting: `Reconnecting (attempt ${this.attempt()})`, closed: 'Stopped',
  })[this.status()]);

  filterChanged$ = new Subject<void>();
  private sub?: Subscription;
  private filterSub = this.filterChanged$.pipe(debounceTime(600)).subscribe(() => this.restart());
  private pendingScroll = false;

  start() {
    this.running.set(true);
    this.lastError.set('');
    this.sub = this.tail.stream({ q: this.q, level: this.levels, service: this.services }).subscribe(ev => {
      if (ev.type === 'status') {
        this.status.set(ev.status);
        this.attempt.set(ev.attempt ?? 0);
        if (ev.status === 'open') this.lastError.set('');
      } else if (ev.type === 'error') {
        this.lastError.set(ev.message);
      } else {
        this.received.update(n => n + ev.hits.length);
        this.events.update(list => {
          const next = list.concat(ev.hits);
          return next.length > this.limit ? next.slice(next.length - this.limit) : next;
        });
        this.pendingScroll = this.autoScroll;
      }
    });
  }

  pause() {
    this.sub?.unsubscribe();
    this.running.set(false);
    this.status.set('closed');
  }

  restart() {
    if (!this.running()) return;
    this.pause();
    this.start();
  }

  clear() { this.events.set([]); }

  loadServices() {
    if (this.serviceOptions().length) return;
    this.api.fieldValues('service', '24h').subscribe(r => this.serviceOptions.set(r.values.map(v => v.key)));
  }

  matches(e: LogHit) {
    return !!this.highlight && e.message?.toLowerCase().includes(this.highlight.toLowerCase());
  }

  onScroll() {
    const el = this.consoleEl?.nativeElement;
    if (!el) return;
    // Pausing auto-scroll when the user scrolls up keeps their place.
    this.autoScroll = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  }

  ngAfterViewChecked() {
    if (this.pendingScroll && this.consoleEl) {
      const el = this.consoleEl.nativeElement;
      el.scrollTop = el.scrollHeight;
      this.pendingScroll = false;
    }
  }

  ngOnDestroy() {
    this.sub?.unsubscribe();
    this.filterSub.unsubscribe();
  }
}
