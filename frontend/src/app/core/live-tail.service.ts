import { Injectable, NgZone, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { apiUrl } from './api-base';
import { queryParams } from './api.service';
import { AuthService } from './auth.service';
import { LogHit, LogQueryParams } from './models';

export type TailEvent =
  | { type: 'status'; status: 'connecting' | 'open' | 'reconnecting' | 'closed'; attempt?: number }
  | { type: 'logs'; hits: LogHit[] }
  | { type: 'error'; message: string };

/**
 * Consumes the API's Server-Sent Events stream with fetch() so the bearer token
 * travels in a header (EventSource cannot set headers, and tokens must not go in URLs).
 * Reconnects with exponential backoff and resumes from the last event id.
 */
@Injectable({ providedIn: 'root' })
export class LiveTailService {
  private auth = inject(AuthService);
  private zone = inject(NgZone);

  stream(query: LogQueryParams): Observable<TailEvent> {
    return new Observable<TailEvent>(observer => {
      const abort = new AbortController();
      let stopped = false;
      let lastId: string | null = null;
      let attempt = 0;

      const emit = (e: TailEvent) => this.zone.run(() => observer.next(e));

      const connect = async () => {
        while (!stopped) {
          emit({ type: 'status', status: attempt ? 'reconnecting' : 'connecting', attempt });
          try {
            let token = this.auth.accessToken;
            const params = queryParams({ ...query, ...(lastId ? { after: lastId } : {}) } as never);
            let resp = await fetch(apiUrl(`/api/logs/live/?${params.toString()}`), {
              headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' }, signal: abort.signal,
            });
            if (resp.status === 401) {
              token = await new Promise<string>((res, rej) => this.auth.refresh().subscribe({ next: res, error: rej }));
              resp = await fetch(apiUrl(`/api/logs/live/?${params.toString()}`), {
                headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' }, signal: abort.signal,
              });
            }
            if (!resp.ok || !resp.body) {
              const body = await resp.json().catch(() => null);
              throw new Error(body?.error?.message ?? `HTTP ${resp.status}`);
            }
            attempt = 0;
            emit({ type: 'status', status: 'open' });
            await this.read(resp.body, (event, data, id) => {
              if (id) lastId = id;
              if (event === 'logs') emit({ type: 'logs', hits: JSON.parse(data) });
              else if (event === 'error') emit({ type: 'error', message: JSON.parse(data).message });
            });
          } catch (err: any) {
            if (stopped || err?.name === 'AbortError') break;
            emit({ type: 'error', message: err?.message ?? 'stream failed' });
          }
          if (stopped) break;
          attempt += 1;
          await new Promise(r => setTimeout(r, Math.min(30000, 1000 * 2 ** Math.min(attempt, 5))));
        }
        emit({ type: 'status', status: 'closed' });
      };

      this.zone.runOutsideAngular(() => connect());
      return () => {
        stopped = true;
        abort.abort();
      };
    });
  }

  /** Minimal text/event-stream parser. */
  private async read(body: ReadableStream<Uint8Array>, onEvent: (event: string, data: string, id: string | null) => void) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      let sep: number;
      while ((sep = buffer.indexOf('\n\n')) >= 0) {
        const chunk = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        let event = 'message', data = '', id: string | null = null;
        for (const line of chunk.split('\n')) {
          if (line.startsWith(':')) continue;
          const idx = line.indexOf(':');
          const field = idx < 0 ? line : line.slice(0, idx);
          const val = idx < 0 ? '' : line.slice(idx + 1).replace(/^ /, '');
          if (field === 'event') event = val;
          else if (field === 'data') data += val;
          else if (field === 'id') id = val;
        }
        if (data) onEvent(event, data, id);
      }
    }
  }
}
