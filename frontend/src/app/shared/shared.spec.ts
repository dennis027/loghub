import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { ThemeService } from '../core/theme.service';
import { LEVEL_COLORS, colorFor, themeChart, timeSeriesOption } from './charts';
import { JsonViewComponent, LevelBadgeComponent, StatusChipComponent } from './ui.components';

describe('Untrusted log rendering', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [NoopAnimationsModule], providers: [provideHttpClient()] }));

  it('renders log content as text, never as HTML (stored XSS)', () => {
    const fixture = TestBed.createComponent(JsonViewComponent);
    const payload = { message: '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>' };
    fixture.componentRef.setInput('value', payload);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('img')).toBeNull();
    expect(el.querySelector('script')).toBeNull();
    expect(el.textContent).toContain('<img src=x');
    expect((window as any).__xss).toBeUndefined();
  });

  it('level badge carries text and icon, not just color', () => {
    const fixture = TestBed.createComponent(LevelBadgeComponent);
    fixture.componentRef.setInput('level', 'critical');
    fixture.detectChanges();
    const span: HTMLElement = fixture.nativeElement.querySelector('span');
    expect(span.textContent).toContain('critical');
    expect(span.className).toContain('level-critical');
  });

  it('status chip falls back to a help icon for unknown states', () => {
    const fixture = TestBed.createComponent(StatusChipComponent);
    fixture.componentRef.setInput('status', 'weird');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('help');
  });
});

describe('chart colors', () => {
  it('uses the reserved status palette for levels', () => {
    expect(colorFor('critical', 5)).toBe(LEVEL_COLORS['critical']);
    expect(colorFor('error', 0)).toBe(LEVEL_COLORS['error']);
  });

  it('assigns categorical slots in fixed order and folds overflow into a neutral', () => {
    expect(colorFor('api', 0)).toBe('#3987e5');
    expect(colorFor('web', 1)).toBe('#d95926');
    expect(colorFor('ninth', 8)).toBe('#898781');
  });

  it('stacks level series in severity order and keeps the legend', () => {
    const opt: any = timeSeriesOption({ interval: '1m', series: ['error', 'info', 'critical'],
      buckets: [{ key: 1, time: 't', count: 3, series: { error: 1, info: 1, critical: 1 } }] });
    expect(opt.series.map((s: any) => s.name)).toEqual(['info', 'error', 'critical']);
    expect(opt.legend.show).not.toBeFalse();
  });
});

describe('light mode', () => {
  it('maps dark chart chrome and categorical colors to light equivalents, keeping status colors and formatters', () => {
    const formatter = (v: number) => `${v}`;
    const dark: any = { textStyle: { color: '#c3c2b7' }, series: [{ itemStyle: { color: '#3987e5' } }, { itemStyle: { color: LEVEL_COLORS['critical'] } }], yAxis: { axisLabel: { formatter } } };
    const light: any = themeChart(dark, 'light');
    expect(light.textStyle.color).toBe('#52514e');
    expect(light.series[0].itemStyle.color).toBe('#2a78d6');
    expect(light.series[1].itemStyle.color).toBe(LEVEL_COLORS['critical']);
    expect(light.yAxis.axisLabel.formatter).toBe(formatter);
    expect(themeChart(dark, 'dark')).toBe(dark);
  });

  it('defaults to dark, toggles, and persists the choice', () => {
    localStorage.removeItem('loghub.theme');
    const service = TestBed.inject(ThemeService);
    expect(service.mode()).toBe('dark');
    service.toggle();
    TestBed.flushEffects();
    expect(document.documentElement.dataset['theme']).toBe('light');
    expect(localStorage.getItem('loghub.theme')).toBe('light');
    service.toggle();
    TestBed.flushEffects();
    expect(document.documentElement.dataset['theme']).toBe('dark');
  });
});
