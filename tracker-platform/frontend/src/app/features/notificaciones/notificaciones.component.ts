import { Component } from '@angular/core';

// no existe en la app vieja -- se añadió al sidebar nuevo siguiendo el
// patron del ejemplo de PrimeNG. Sin backend de notificaciones todavia,
// asi que de momento es solo el estado vacio.
@Component({
  selector: 'app-notificaciones',
  standalone: true,
  template: `
    <div class="mb-3.5 font-display text-lg font-semibold">Notificaciones</div>
    <div class="panel flex flex-col items-center gap-2 p-panel py-16 text-center">
      <i class="pi pi-bell text-2xl text-fg-muted"></i>
      <div class="text-base text-fg-muted">No tienes notificaciones todavía.</div>
    </div>
  `,
})
export class NotificacionesComponent {}
