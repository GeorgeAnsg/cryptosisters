import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { Auth, authState } from '@angular/fire/auth';
import { map, take } from 'rxjs';

// aplicado a la ruta raiz del shell (app.routes.ts) -- espera la PRIMERA
// emision del estado de Firebase (take(1)) antes de decidir, asi que en un
// refresh con sesion guardada no hay parpadeo hacia /login
export const authGuard: CanActivateFn = () => {
  const router = inject(Router);
  return authState(inject(Auth)).pipe(
    take(1),
    map((usuario) => !!usuario || router.createUrlTree(['/login'])),
  );
};
