import { Routes } from '@angular/router';
import { ShellComponent } from './layout/shell/shell.component';
import { authGuard } from './core/auth/auth.guard';

// Cada feature carga su componente de forma perezosa (loadComponent) --
// nada de una feature se descarga hasta que el usuario entra en su pestaña.
// Al añadir una feature nueva: carpeta en features/<nombre>/, componente
// standalone, y una linea aqui.
export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login.component').then((m) => m.LoginComponent),
  },
  {
    path: '',
    component: ShellComponent,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      {
        path: 'dashboard',
        loadComponent: () => import('./features/dashboard/dashboard.component').then((m) => m.DashboardComponent),
      },
      {
        path: 'traders',
        loadComponent: () => import('./features/traders/traders.component').then((m) => m.TradersComponent),
      },
      {
        path: 'mis-posiciones',
        loadComponent: () => import('./features/mis-posiciones/mis-posiciones.component').then((m) => m.MisPosicionesComponent),
      },
      {
        path: 'consenso',
        loadComponent: () => import('./features/consenso/consenso.component').then((m) => m.ConsensoComponent),
      },
      {
        path: 'mercado',
        loadComponent: () => import('./features/mercado/mercado.component').then((m) => m.MercadoComponent),
      },
      {
        path: 'estadisticas',
        loadComponent: () => import('./features/estadisticas/estadisticas.component').then((m) => m.EstadisticasComponent),
      },
      {
        path: 'notificaciones',
        loadComponent: () => import('./features/notificaciones/notificaciones.component').then((m) => m.NotificacionesComponent),
      },
    ],
  },
];
