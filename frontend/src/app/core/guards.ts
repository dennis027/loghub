import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map } from 'rxjs';
import { AuthService } from './auth.service';
import { Role } from './models';

export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.isAuthenticated()) return true;
  return auth.restore().pipe(
    map(ok => ok || router.createUrlTree(['/login'], { queryParams: { next: state.url } })),
  );
};

export function roleGuard(min: Role): CanActivateFn {
  return () => {
    const auth = inject(AuthService);
    return auth.hasRole(min) || inject(Router).createUrlTree(['/overview']);
  };
}
