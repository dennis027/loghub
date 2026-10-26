export type Role = 'admin' | 'editor' | 'analyst' | 'viewer';
export type Level = 'debug' | 'info' | 'warning' | 'error' | 'critical';

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface CurrentUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: Role;
  is_staff: boolean;
  organization: { id: number; name: string; slug: string } | null;
  preferences: { timezone: string; default_time_range: string; live_event_limit: number };
}

export interface LogHit {
  id: string;
  index?: string;
  timestamp: string;
  level: Level | string | null;
  service: string | null;
  environment: string | null;
  hostname: string | null;
  container: string | null;
  source_id: string | null;
  message: string;
  trace_id: string | null;
  demo: boolean;
  source: Record<string, unknown>;
}

export interface SearchResponse {
  provider: string;
  executed_by: string;
  external_url: string | null;
  total: number;
  total_relation: string;
  took_ms: number;
  timed_out: boolean;
  cursor: string | null;
  hits: LogHit[];
}

export interface FieldFilter { field: string; op: string; value?: unknown }

export interface LogQueryParams {
  q?: string;
  mode?: 'simple' | 'lucene';
  provider?: string;
  range?: string;
  start?: string;
  end?: string;
  service?: string[];
  environment?: string[];
  level?: string[];
  hostname?: string[];
  container?: string[];
  source_id?: string[];
  event_type?: string[];
  source_type?: string[];
  field_filters?: FieldFilter[];
  size?: number;
  cursor?: string | null;
  order?: 'asc' | 'desc';
}

export interface Bucket { key: string | number; count: number; value?: number | null }
export interface HistogramBucket { key: number; time: string; count: number; series?: Record<string, number>; value?: number }
export interface Histogram { interval: string; buckets: HistogramBucket[]; series: string[] }

export interface AggSpec {
  type: 'histogram' | 'terms' | 'metric';
  field?: string;
  size?: number;
  interval?: string;
  split_by?: string;
  split_size?: number;
  metric?: string;
  metric_field?: string;
  filter?: Record<string, unknown>;
}

export interface LogSource {
  id: number;
  name: string;
  description: string;
  source_type: string;
  environment: string;
  hostname: string;
  endpoint: string;
  owner: number | null;
  owner_username: string | null;
  team: number | null;
  log_route: 'elk' | 'graylog' | 'both';
  match_field: string;
  match_value: string;
  effective_match_value: string;
  source_key: string;
  stale_after_minutes: number;
  enabled: boolean;
  status: 'pending' | 'active' | 'stale' | 'disabled';
  last_seen: string | null;
  events_24h: number;
  has_token: boolean;
  token_prefix: string;
  created_at: string;
}

export interface InstructionStep { title: string; description: string; language: string; filename: string | null; content: string }

export interface Collector {
  id: number; name: string; collector_type: string; endpoint: string; managed: boolean; status: string;
  status_message: string; last_heartbeat: string | null; metrics: Record<string, any>;
}

export interface Integration {
  id: number; provider: string; name: string; description: string; enabled: boolean; public_url: string;
  status: string; status_message: string; version: string; latency_ms: number | null;
  details: Record<string, any>; last_checked: string | null;
}

export interface AlertRule {
  id?: number;
  name: string;
  description: string;
  category: 'operational' | 'security';
  rule_type: 'threshold' | 'spike' | 'absence' | 'storage';
  severity: 'info' | 'warning' | 'error' | 'critical';
  enabled: boolean;
  query: string;
  query_mode: 'simple' | 'lucene';
  filters: Record<string, string[]>;
  field_filters: FieldFilter[];
  source: number | null;
  window_minutes: number;
  comparator: 'gt' | 'gte' | 'lt' | 'lte';
  threshold: number;
  spike_factor: number;
  min_count: number;
  evaluation_interval_seconds: number;
  cooldown_minutes: number;
  channels: number[];
  last_evaluated_at?: string | null;
  last_value?: number | null;
  last_state?: string;
  last_error?: string;
  open_events?: number;
}

export interface AlertEvent {
  id: number; rule: number | null; rule_name: string; status: 'firing' | 'acknowledged' | 'resolved';
  severity: string; category: string; title: string; message: string; value: number | null; threshold: number | null;
  occurrences: number; samples: Partial<LogHit>[]; context: Record<string, any>; started_at: string;
  last_seen_at: string; resolved_at: string | null; acknowledged_by: string | null; acknowledged_at: string | null;
  note: string; deliveries: { channel: string; kind: string; status: string; attempts: number; error: string; sent_at: string | null }[];
}

export interface NotificationChannel {
  id?: number; name: string; channel_type: 'email' | 'webhook'; config: Record<string, any>; secret?: string;
  has_secret?: boolean; enabled: boolean; send_resolved: boolean;
}

export interface Widget {
  id: string;
  title: string;
  type: 'stat' | 'timeseries' | 'bar' | 'pie' | 'table' | 'logs';
  source: 'logs' | 'prometheus';
  query: Partial<LogQueryParams>;
  agg?: AggSpec;
  promql?: string;
  unit?: string;
  layout: { cols: number };
}

export interface Dashboard {
  id?: number; name: string; description: string; folder: string; category: string; widgets: Widget[];
  time_range: string; grafana_uid: string; is_template?: boolean; created_by?: string | null; updated_at?: string;
}

export interface SavedSearch {
  id?: number; name: string; description: string; provider: string; query: string; query_mode: string;
  filters: Record<string, string[]>; field_filters: FieldFilter[]; time_range: string; is_shared: boolean;
  created_by?: string | null;
}

export interface RetentionPolicy {
  id: number; target: string; name: string; rollover_days: number; delete_after_days: number; is_active: boolean;
  sync_status: string; sync_message: string; last_synced_at: string | null; updated_by: string | null;
}

export interface AuditEvent {
  id: number; actor_username: string; action: string; target_type: string; target_id: string; target_repr: string;
  changes: Record<string, unknown>; ip_address: string | null; user_agent: string; request_id: string; created_at: string;
}

export interface User {
  id?: number; username: string; email: string; first_name: string; last_name: string; role: Role;
  is_active: boolean; teams: number[]; password?: string; last_login?: string | null;
}

export interface Team { id?: number; name: string; description: string; member_count?: number }
