import { Routes } from '@angular/router';
import { authGuard, roleGuard } from './core/guards';
import { ShellComponent } from './layout/shell.component';

export const routes: Routes = [
  { path: 'login', loadComponent: () => import('./pages/login.component').then(m => m.LoginComponent), title: 'Sign in · LogHub' },
  {
    path: '',
    component: ShellComponent,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'overview' },
      { path: 'overview', title: 'Overview · LogHub', loadComponent: () => import('./pages/overview.component').then(m => m.OverviewComponent) },
      { path: 'explore', title: 'Log Explorer · LogHub', loadComponent: () => import('./pages/log-explorer.component').then(m => m.LogExplorerComponent) },
      { path: 'live', title: 'Live Logs · LogHub', loadComponent: () => import('./pages/live-logs.component').then(m => m.LiveLogsComponent) },
      { path: 'dashboards', title: 'Dashboards · LogHub', loadComponent: () => import('./pages/dashboards.component').then(m => m.DashboardsComponent) },
      { path: 'dashboards/:id', title: 'Dashboard · LogHub', loadComponent: () => import('./pages/dashboard-view.component').then(m => m.DashboardViewComponent) },
      { path: 'sources', title: 'Log Sources · LogHub', loadComponent: () => import('./pages/log-sources.component').then(m => m.LogSourcesComponent) },
      { path: 'services', title: 'Applications & Services · LogHub', loadComponent: () => import('./pages/services.component').then(m => m.ServicesComponent) },
      { path: 'infrastructure', title: 'Infrastructure · LogHub', loadComponent: () => import('./pages/infrastructure.component').then(m => m.InfrastructureComponent) },
      { path: 'alerts', title: 'Alerts · LogHub', loadComponent: () => import('./pages/alerts.component').then(m => m.AlertsComponent) },
      { path: 'alerts/events/:id', title: 'Alert · LogHub', loadComponent: () => import('./pages/alert-event.component').then(m => m.AlertEventComponent) },
      { path: 'detections', title: 'Detection Rules · LogHub', data: { category: 'security' }, loadComponent: () => import('./pages/rules.component').then(m => m.RulesComponent) },
      { path: 'rules', title: 'Alert Rules · LogHub', data: { category: 'operational' }, loadComponent: () => import('./pages/rules.component').then(m => m.RulesComponent) },
      { path: 'pipelines', title: 'Log Pipelines · LogHub', loadComponent: () => import('./pages/pipelines.component').then(m => m.PipelinesComponent) },
      { path: 'retention', title: 'Retention · LogHub', loadComponent: () => import('./pages/retention.component').then(m => m.RetentionComponent) },
      { path: 'integrations', title: 'Integrations · LogHub', loadComponent: () => import('./pages/integrations.component').then(m => m.IntegrationsComponent) },
      { path: 'reports', title: 'Reports · LogHub', loadComponent: () => import('./pages/reports.component').then(m => m.ReportsComponent) },
      { path: 'audit', title: 'Audit Logs · LogHub', canActivate: [roleGuard('admin')], loadComponent: () => import('./pages/audit.component').then(m => m.AuditComponent) },
      { path: 'users', title: 'Users & Roles · LogHub', canActivate: [roleGuard('admin')], loadComponent: () => import('./pages/users.component').then(m => m.UsersComponent) },
      { path: 'settings', title: 'Settings · LogHub', loadComponent: () => import('./pages/settings.component').then(m => m.SettingsComponent) },
    ],
  },
  { path: '**', redirectTo: '' },
];
