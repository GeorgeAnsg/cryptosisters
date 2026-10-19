import { inject } from '@angular/core';
import { HttpInterceptorFn } from '@angular/common/http';
import { finalize } from 'rxjs';
import { LoadingService } from './loading.service';

// cada peticion HTTP real (cuando el backend sustituya a los mocks) activa
// el loader global de app.component -- nada que montar a mano en cada
// componente que haga una llamada.
export const loadingInterceptor: HttpInterceptorFn = (req, next) => {
  const loading = inject(LoadingService);
  loading.empezar();
  return next(req).pipe(finalize(() => loading.terminar()));
};
