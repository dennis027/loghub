import { Clipboard } from '@angular/cdk/clipboard';
import { DatePipe, JsonPipe } from '@angular/common';
import { Component, Input, computed, inject, input } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import type { EChartsOption } from 'echarts';
import { NgxEchartsDirective } from 'ngx-echarts';
import { ThemeService } from '../core/theme.service';
import { Notify } from '../core/ui';
import { themeChart } from './charts';

const LEVEL_ICONS: Record<string, string> = {
  critical: 'report', error: 'error', warning: 'warning', info: 'info', debug: 'bug_report',
};

/** Log level badge: color + icon + text, so meaning never depends on color alone. */
@Component({
  selector: 'lh-level',
  standalone: true,
  imports: [MatIconModule],
  template: `<span class="level level-{{ level() || 'unknown' }}"><mat-icon inline>{{ icon() }}</mat-icon>{{ level() || 'n/a' }}</span>`,
})
export class LevelBadgeComponent {
  level = input<string | null | undefined>();
  icon = computed(() => LEVEL_ICONS[this.level() ?? ''] ?? 'help');
}

const STATUS_ICONS: Record<string, string> = {
  healthy: 'check_circle', active: 'check_circle', sent: 'check_circle', ok: 'check_circle', synced: 'check_circle',
  degraded: 'warning', stale: 'schedule', pending: 'hourglass_empty', acknowledged: 'visibility', unknown: 'help',
  unhealthy: 'cancel', failed: 'cancel', firing: 'notifications_active', error: 'cancel', disabled: 'block',
  resolved: 'task_alt',
};

@Component({
  selector: 'lh-status',
  standalone: true,
  imports: [MatIconModule],
  template: `<span class="status status-{{ status() }}"><mat-icon inline>{{ icon() }}</mat-icon>{{ label() || status() }}</span>`,
})
export class StatusChipComponent {
  status = input<string>('unknown');
  label = input<string>();
  icon = computed(() => STATUS_ICONS[this.status()] ?? 'help');
}

@Component({
  selector: 'lh-empty',
  standalone: true,
  imports: [MatIconModule],
  template: `
    <div class="empty-state">
      <mat-icon>{{ icon }}</mat-icon>
      <div class="empty-title">{{ title }}</div>
      <div class="empty-text"><ng-content /></div>
    </div>`,
})
export class EmptyStateComponent {
  @Input() icon = 'inbox';
  @Input() title = 'Nothing here yet';
}

@Component({
  selector: 'lh-page-header',
  standalone: true,
  template: `
    <header class="page-header">
      <div>
        <h1>{{ title }}</h1>
        @if (subtitle) { <p class="subtitle">{{ subtitle }}</p> }
      </div>
      <div class="page-actions"><ng-content /></div>
    </header>`,
})
export class PageHeaderComponent {
  @Input({ required: true }) title!: string;
  @Input() subtitle?: string;
}

@Component({
  selector: 'lh-chart',
  standalone: true,
  imports: [NgxEchartsDirective],
  template: `<div echarts [options]="themed()" [autoResize]="true" class="chart" [style.height.px]="height()"></div>`,
})
export class ChartComponent {
  options = input.required<EChartsOption>();
  height = input(260);
  private theme = inject(ThemeService);
  /** Re-colors instantly when the user switches theme. */
  themed = computed(() => themeChart(this.options(), this.theme.mode()));
}

@Component({
  selector: 'lh-copy',
  standalone: true,
  imports: [MatButtonModule, MatIconModule, MatTooltipModule],
  template: `<button mat-icon-button type="button" (click)="copy($event)" [matTooltip]="label" [attr.aria-label]="label"><mat-icon>content_copy</mat-icon></button>`,
})
export class CopyButtonComponent {
  @Input({ required: true }) text!: string;
  @Input() label = 'Copy to clipboard';
  private clipboard = inject(Clipboard);
  private notify = inject(Notify);
  copy(e: Event) {
    e.stopPropagation();
    if (this.clipboard.copy(this.text)) this.notify.ok('Copied to clipboard');
  }
}

/** Raw JSON view. Rendered with text interpolation only: untrusted log content is never parsed as HTML. */
@Component({
  selector: 'lh-json',
  standalone: true,
  imports: [JsonPipe, CopyButtonComponent],
  template: `
    <div class="json-view">
      <lh-copy class="json-copy" [text]="asText()" label="Copy JSON" />
      <pre>{{ value() | json }}</pre>
    </div>`,
})
export class JsonViewComponent {
  value = input<unknown>();
  asText = computed(() => JSON.stringify(this.value(), null, 2));
}

@Component({
  selector: 'lh-stat',
  standalone: true,
  imports: [MatIconModule, DatePipe],
  template: `
    <div class="stat-tile" [class.stat-alert]="tone === 'alert'" [class.stat-warn]="tone === 'warn'">
      <div class="stat-label">@if (icon) {<mat-icon inline>{{ icon }}</mat-icon>} {{ label }}</div>
      <div class="stat-value">{{ value }}</div>
      @if (hint) { <div class="stat-hint">{{ hint }}</div> }
    </div>`,
})
export class StatTileComponent {
  @Input({ required: true }) label!: string;
  @Input() value: string | number | null = '—';
  @Input() hint?: string;
  @Input() icon?: string;
  @Input() tone: 'normal' | 'warn' | 'alert' = 'normal';
}
