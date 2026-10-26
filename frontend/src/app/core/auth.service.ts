import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, catchError, finalize, map, of, shareReplay, switchMap, tap, throwError } from 'rxjs';
import { CurrentUser, Role } from './models';

const RANK: Record<Role, number> = { viewer: 0, analyst: 1, editor: 2, admin: 3 };
const REFRESH_KEY = 'loghub.refresh';

interface TokenPair { access: string; refresh?: string }

/**
 * JWT session. The short-lived access token lives only in memory; the refresh
 * token is kept in sessionStorage (cleared when the tab closes) so a reload
 * does not log the user out.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);
  private access: string | null = null;
  private refreshing$: Observable<string> | null = null;

  readonly user = signal<CurrentUser | null>(null);
  readonly isAuthenticated = computed(() => this.user() !== null);

  get accessToken(): string | null {
    return this.access;
  }

  hasRole(min: Role): boolean {
    const u = this.user();
    return !!u && RANK[u.role] >= RANK[min];
  }

  login(username: string, password: string): Observable<CurrentUser> {
    return this.http.post<TokenPair>('/api/auth/login/', { username, password }).pipe(
      tap(tokens => this.store(tokens)),
      switchMap(() => this.loadUser()),
    );
  }

  /** Restore a session on startup from the stored refresh token, if any. */
  restore(): Observable<boolean> {
    if (!this.storedRefresh()) return of(false);
    return this.refresh().pipe(
      switchMap(() => this.loadUser()),
      map(() => true),
      catchError(() => {
        this.clear();
        return of(false);
      }),
    );
  }

  loadUser(): Observable<CurrentUser> {
    return this.http.get<CurrentUser>('/api/auth/me/').pipe(tap(u => this.user.set(u)));
  }

  refresh(): Observable<string> {
    const refresh = this.storedRefresh();
    if (!refresh) return throwError(() => new Error('no refresh token'));
    if (!this.refreshing$) {
      this.refreshing$ = this.http.post<TokenPair>('/api/auth/refresh/', { refresh }).pipe(
        tap(tokens => this.store(tokens)),
        map(tokens => tokens.access),
        finalize(() => (this.refreshing$ = null)),
        shareReplay(1),
      );
    }
    return this.refreshing$;
  }

  logout(): void {
    const refresh = this.storedRefresh();
    const done = () => {
      this.clear();
      this.router.navigate(['/login']);
    };
    if (refresh && this.access) {
      this.http.post('/api/auth/logout/', { refresh }).subscribe({ complete: done, error: done });
    } else {
      done();
    }
  }

  sessionExpired(): void {
    this.clear();
    this.router.navigate(['/login'], { queryParams: { expired: 1 } });
  }

  private store(tokens: TokenPair) {
    this.access = tokens.access;
    if (tokens.refresh) {
      try { sessionStorage.setItem(REFRESH_KEY, tokens.refresh); } catch { /* storage unavailable */ }
    }
  }

  private storedRefresh(): string | null {
    try { return sessionStorage.getItem(REFRESH_KEY); } catch { return null; }
  }

  private clear() {
    this.access = null;
    this.user.set(null);
    try { sessionStorage.removeItem(REFRESH_KEY); } catch { /* ignore */ }
  }
}
