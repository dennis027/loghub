import { HttpInterceptorFn } from '@angular/common/http';

declare global {
  interface Window { LOGHUB_API_URL?: string }
}

/** Origin of the API when the console is hosted apart from it (e.g. GitHub Pages). Empty means same origin. */
export const API_BASE = (window.LOGHUB_API_URL ?? '').replace(/\/+$/, '');

export const apiUrl = (path: string) => API_BASE + path;

/** Must run after authInterceptor, which matches on the relative `/api/` prefix. */
export const apiBaseInterceptor: HttpInterceptorFn = (req, next) =>
  API_BASE && req.url.startsWith('/api/') ? next(req.clone({ url: API_BASE + req.url })) : next(req);
