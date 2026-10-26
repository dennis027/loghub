import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';

export const TIME_RANGES = [
  { value: '15m', label: 'Last 15 minutes' },
  { value: '1h', label: 'Last hour' },
  { value: '6h', label: 'Last 6 hours' },
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
];

export const LEVELS = ['debug', 'info', 'warning', 'error', 'critical'];

/** Readable message from the API's {"error": {...}} envelope. */
export function errorMessage(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    const e = err.error?.error;
    if (e?.details && typeof e.details === 'object') {
      const first = Object.entries(e.details)[0];
      if (first) return `${first[0]}: ${Array.isArray(first[1]) ? first[1].join(' ') : JSON.stringify(first[1])}`;
    }
    if (e?.message) return e.message;
    if (err.status === 0) return 'The API is unreachable.';
    return `Request failed (${err.status}).`;
  }
  return (err as Error)?.message ?? 'Unexpected error.';
}

@Injectable({ providedIn: 'root' })
export class Notify {
  private snack = inject(MatSnackBar);
  ok(message: string) { this.snack.open(message, 'OK', { duration: 3000 }); }
  error(err: unknown) { this.snack.open(errorMessage(err), 'Dismiss', { duration: 6000, panelClass: 'snack-error' }); }
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0, v = bytes;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return new Intl.NumberFormat('en', { notation: n >= 100000 ? 'compact' : 'standard', maximumFractionDigits: 2 }).format(n);
}
