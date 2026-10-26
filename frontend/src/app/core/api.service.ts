import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  AggSpec, AlertEvent, AlertRule, AuditEvent, Collector, Dashboard, InstructionStep, Integration, LogHit, LogQueryParams,
  LogSource, NotificationChannel, Paginated, RetentionPolicy, SavedSearch, SearchResponse, Team, User,
} from './models';

/** Serializes a log query into HTTP params (lists repeat; field_filters as JSON). */
export function queryParams(q: LogQueryParams & Record<string, unknown>): HttpParams {
  let params = new HttpParams();
  for (const [key, value] of Object.entries(q)) {
    if (value === undefined || value === null || value === '') continue;
    if (key === 'field_filters') {
      if ((value as unknown[]).length) params = params.set(key, JSON.stringify(value));
    } else if (Array.isArray(value)) {
      value.forEach(v => (params = params.append(key, String(v))));
    } else {
      params = params.set(key, String(value));
    }
  }
  return params;
}

/** CRUD helper for a DRF ModelViewSet. */
class Resource<T extends { id?: number }> {
  constructor(private http: HttpClient, private base: string) {}
  list(params: Record<string, string | number> = {}): Observable<Paginated<T>> {
    return this.http.get<Paginated<T>>(this.base, { params });
  }
  get(id: number): Observable<T> { return this.http.get<T>(`${this.base}${id}/`); }
  create(body: Partial<T>): Observable<T> { return this.http.post<T>(this.base, body); }
  update(id: number, body: Partial<T>): Observable<T> { return this.http.patch<T>(`${this.base}${id}/`, body); }
  remove(id: number): Observable<void> { return this.http.delete<void>(`${this.base}${id}/`); }
  action<R>(id: number | null, name: string, body: unknown = {}, method: 'get' | 'post' = 'post'): Observable<R> {
    const url = id === null ? `${this.base}${name}/` : `${this.base}${id}/${name}/`;
    return method === 'get' ? this.http.get<R>(url) : this.http.post<R>(url, body);
  }
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  readonly sources = new Resource<LogSource>(this.http, '/api/log-sources/');
  readonly collectors = new Resource<Collector>(this.http, '/api/collectors/');
  readonly rules = new Resource<AlertRule>(this.http, '/api/alert-rules/');
  readonly events = new Resource<AlertEvent>(this.http, '/api/alert-events/');
  readonly channels = new Resource<NotificationChannel>(this.http, '/api/notification-channels/');
  readonly dashboards = new Resource<Dashboard>(this.http, '/api/dashboards/');
  readonly savedSearches = new Resource<SavedSearch>(this.http, '/api/saved-searches/');
  readonly users = new Resource<User>(this.http, '/api/users/');
  readonly teams = new Resource<Team>(this.http, '/api/teams/');
  readonly audit = new Resource<AuditEvent & { id: number }>(this.http, '/api/audit-events/');

  search(q: LogQueryParams): Observable<SearchResponse> {
    return this.http.get<SearchResponse>('/api/logs/search/', { params: queryParams(q as never) });
  }

  aggregate<T = Record<string, any>>(q: LogQueryParams, aggs: Record<string, AggSpec>): Observable<T> {
    return this.http.post<T>('/api/logs/aggregate/', { ...q, aggs });
  }

  event(id: string): Observable<{ event: LogHit; context: LogHit[]; trace: LogHit[] }> {
    return this.http.get<any>(`/api/logs/events/${encodeURIComponent(id)}/`, { params: { context: 'true' } });
  }

  fieldValues(field: string, range = '24h'): Observable<{ field: string; values: { key: string; count: number }[] }> {
    return this.http.get<any>(`/api/logs/fields/${encodeURIComponent(field)}/values/`, { params: { range } });
  }

  exportLogs(q: LogQueryParams, format: 'csv' | 'json'): Observable<Blob> {
    return this.http.get('/api/logs/export/', { params: queryParams({ ...q, format } as never), responseType: 'blob' });
  }

  overview(range: string): Observable<any> { return this.http.get('/api/stats/overview/', { params: { range } }); }
  services(range: string): Observable<any> { return this.http.get('/api/services/', { params: { range } }); }
  infrastructure(): Observable<any> { return this.http.get('/api/infrastructure/'); }
  metricsRange(query: string, range: string): Observable<any> {
    return this.http.get('/api/metrics/query_range/', { params: { query, range } });
  }
  platformHealth(): Observable<any> { return this.http.get('/api/health/'); }
  pipelines(): Observable<any> { return this.http.get('/api/pipelines/status/'); }

  integrations(): Observable<Integration[]> { return this.http.get<Integration[]>('/api/integrations/'); }
  checkIntegration(provider: string): Observable<Integration> {
    return this.http.post<Integration>(`/api/integrations/${provider}/check/`, {});
  }
  updateIntegration(provider: string, body: Partial<Integration>): Observable<Integration> {
    return this.http.patch<Integration>(`/api/integrations/${provider}/`, body);
  }
  graylogOverview(): Observable<any> { return this.http.get('/api/integrations/graylog/overview/'); }

  sourceInstructions(id: number): Observable<{ source: string; steps: InstructionStep[] }> {
    return this.http.get<any>(`/api/log-sources/${id}/instructions/`);
  }

  retention(): Observable<RetentionPolicy[]> { return this.http.get<RetentionPolicy[]>('/api/retention-policies/'); }
  updateRetention(id: number, body: Partial<RetentionPolicy>): Observable<RetentionPolicy> {
    return this.http.patch<RetentionPolicy>(`/api/retention-policies/${id}/`, body);
  }
  retentionLive(id: number): Observable<any> { return this.http.get(`/api/retention-policies/${id}/live/`); }

  reports(): Observable<{ key: string; title: string }[]> { return this.http.get<any>('/api/reports/'); }
  report(key: string, range: string): Observable<any> { return this.http.get(`/api/reports/${key}/`, { params: { range } }); }
  reportFile(key: string, range: string, format: 'csv' | 'pdf'): Observable<Blob> {
    return this.http.get(`/api/reports/${key}/`, { params: { range, format }, responseType: 'blob' });
  }

  organization(): Observable<any> { return this.http.get('/api/organization/'); }
  updateOrganization(body: unknown): Observable<any> { return this.http.patch('/api/organization/', body); }
  updatePreferences(body: unknown): Observable<any> { return this.http.patch('/api/auth/me/preferences/', body); }
  changePassword(current_password: string, new_password: string): Observable<void> {
    return this.http.post<void>('/api/auth/me/password/', { current_password, new_password });
  }
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
