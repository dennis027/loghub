import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { queryParams } from './api.service';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';
import { LiveTailService } from './live-tail.service';
import { errorMessage } from './ui';
import { HttpErrorResponse } from '@angular/common/http';

const USER = {
  id: 1, username: 'ana', email: '', first_name: '', last_name: '', role: 'analyst', is_staff: false,
  organization: { id: 1, name: 'Acme', slug: 'acme' },
  preferences: { timezone: 'UTC', default_time_range: '1h', live_event_limit: 500 },
};

describe('AuthService + interceptor', () => {
  let http: HttpTestingController;
  let auth: AuthService;
  let client: HttpClient;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
    client = TestBed.inject(HttpClient);
    spyOn(TestBed.inject(Router), 'navigate').and.resolveTo(true);
  });

  afterEach(() => http.verify());

  function login() {
    auth.login('ana', 'pw').subscribe();
    http.expectOne('/api/auth/login/').flush({ access: 'A1', refresh: 'R1' });
    const me = http.expectOne('/api/auth/me/');
    expect(me.request.headers.get('Authorization')).toBe('Bearer A1');
    me.flush(USER);
  }

  it('logs in, keeps the access token in memory and the refresh token in sessionStorage', () => {
    login();
    expect(auth.isAuthenticated()).toBeTrue();
    expect(auth.accessToken).toBe('A1');
    expect(sessionStorage.getItem('loghub.refresh')).toBe('R1');
    expect(localStorage.getItem('loghub.refresh')).toBeNull();
  });

  it('enforces role ranks', () => {
    login();
    expect(auth.hasRole('viewer')).toBeTrue();
    expect(auth.hasRole('analyst')).toBeTrue();
    expect(auth.hasRole('editor')).toBeFalse();
  });

  it('does not send the token on the login call', () => {
    auth.login('ana', 'pw').subscribe({ error: () => undefined });
    const req = http.expectOne('/api/auth/login/');
    expect(req.request.headers.has('Authorization')).toBeFalse();
    req.flush({}, { status: 401, statusText: 'Unauthorized' });
  });

  it('refreshes once on 401 and retries the original request', () => {
    login();
    let body: unknown;
    client.get('/api/log-sources/').subscribe(b => (body = b));
    http.expectOne('/api/log-sources/').flush({}, { status: 401, statusText: 'Unauthorized' });
    http.expectOne('/api/auth/refresh/').flush({ access: 'A2', refresh: 'R2' });
    const retry = http.expectOne('/api/log-sources/');
    expect(retry.request.headers.get('Authorization')).toBe('Bearer A2');
    retry.flush({ ok: true });
    expect(body).toEqual({ ok: true });
  });

  it('clears the session when refresh fails', () => {
    login();
    client.get('/api/log-sources/').subscribe({ error: () => undefined });
    http.expectOne('/api/log-sources/').flush({}, { status: 401, statusText: 'Unauthorized' });
    http.expectOne('/api/auth/refresh/').flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(auth.isAuthenticated()).toBeFalse();
    expect(sessionStorage.getItem('loghub.refresh')).toBeNull();
  });
});

describe('queryParams', () => {
  it('repeats list params, JSON-encodes field filters and drops empties', () => {
    const p = queryParams({ q: 'err', level: ['error', 'critical'], service: [], field_filters: [{ field: 'http.status', op: 'gte', value: 500 }], cursor: null } as never);
    expect(p.getAll('level')).toEqual(['error', 'critical']);
    expect(p.has('service')).toBeFalse();
    expect(p.has('cursor')).toBeFalse();
    expect(JSON.parse(p.get('field_filters')!)).toEqual([{ field: 'http.status', op: 'gte', value: 500 }]);
  });
});

describe('errorMessage', () => {
  it('reads the API error envelope, preferring field details', () => {
    const err = new HttpErrorResponse({ status: 400, error: { error: { code: 'validation_error', message: 'Validation failed.', details: { name: ['Required.'] } } } });
    expect(errorMessage(err)).toBe('name: Required.');
    expect(errorMessage(new HttpErrorResponse({ status: 0 }))).toBe('The API is unreachable.');
  });
});

describe('LiveTailService SSE parser', () => {
  it('parses events, data and ids across chunk boundaries', async () => {
    TestBed.configureTestingModule({ providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()] });
    const svc = TestBed.inject(LiveTailService) as any;
    const enc = new TextEncoder();
    const chunks = ['retry: 3000\n\n: keepalive\n\nid: 12:ab\nevent: lo', 'gs\ndata: [{"id":"1"}]\n\n'];
    const stream = new ReadableStream<Uint8Array>({ start(c) { chunks.forEach(ch => c.enqueue(enc.encode(ch))); c.close(); } });
    const seen: [string, string, string | null][] = [];
    await svc.read(stream, (e: string, d: string, id: string | null) => seen.push([e, d, id]));
    expect(seen).toEqual([['logs', '[{"id":"1"}]', '12:ab']]);
  });
});
