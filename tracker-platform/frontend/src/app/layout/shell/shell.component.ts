import { Component, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { Avatar } from 'primeng/avatar';
import { Drawer } from 'primeng/drawer';
import { IconButtonComponent } from '../../shared/components/icon-button/icon-button.component';
import { AuthService } from '../../core/auth/auth.service';
import { NotificacionesService } from '../../core/notificaciones/notificaciones.service';

interface SubItemNav {
  etiqueta: string;
  vista: string;
}

interface ItemNav {
  ruta: string;
  etiqueta: string;
  icono: string;
  hijos?: SubItemNav[];
}

// Cascaron de la app: layout a pantalla completa, sidebar fijo a la
// izquierda (desktop) + contenido a la derecha. En movil el sidebar se
// sustituye por un p-drawer de PrimeNG (sandwich); ambos comparten el
// mismo <ng-template #enlacesNav> para no duplicar el estado activo/
// inactivo en dos sitios.
@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, NgTemplateOutlet, IconButtonComponent, Avatar, Drawer],
  templateUrl: './shell.component.html',
})
export class ShellComponent {
  readonly navegacion: ItemNav[] = [
    { ruta: '/dashboard', etiqueta: 'Dashboard', icono: 'pi pi-home' },
    {
      ruta: '/traders',
      etiqueta: 'Traders',
      icono: 'pi pi-users',
      hijos: [
        { etiqueta: 'Trading', vista: 'trading' },
        { etiqueta: 'Spot', vista: 'spot' },
        { etiqueta: 'Posiciones', vista: 'posiciones' },
        { etiqueta: 'Cribado', vista: 'cribado' },
      ],
    },
    { ruta: '/mis-posiciones', etiqueta: 'Mis Posiciones', icono: 'pi pi-wallet' },
    { ruta: '/consenso', etiqueta: 'Consenso', icono: 'pi pi-bolt' },
    { ruta: '/mercado', etiqueta: 'Mercado', icono: 'pi pi-chart-line' },
    { ruta: '/estadisticas', etiqueta: 'Estadísticas', icono: 'pi pi-chart-bar' },
    { ruta: '/notificaciones', etiqueta: 'Notificaciones', icono: 'pi pi-bell' },
  ];

  protected readonly menuAbierto = signal(false);
  // sidebar fijo (desktop) colapsable a una franja de solo iconos -- boton
  // dentro del propio sidebar, como el de PrimeNG
  protected readonly sidebarColapsado = signal(false);

  constructor(
    protected readonly auth: AuthService,
    protected readonly notificaciones: NotificacionesService,
    private readonly router: Router,
  ) {}

  protected async salir() {
    await this.auth.logout();
    this.router.navigateByUrl('/login');
  }
}
