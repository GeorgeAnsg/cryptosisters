import { Component, inject } from '@angular/core';
import { Button } from 'primeng/button';
import { NotificacionesService } from '../../core/notificaciones/notificaciones.service';
import { PushService } from '../../core/push/push.service';
import { tiempoRelativo } from '../../shared/utils/tiempo-relativo';

@Component({
  selector: 'app-notificaciones',
  standalone: true,
  imports: [Button],
  template: `
    <div class="mb-3.5 flex flex-wrap items-center justify-between gap-2.5">
      <div class="font-display text-lg font-semibold">Notificaciones</div>
      @if (push.disponible) {
        @if (push.suscrito()) {
          <p-button label="Avisos activados" icon="pi pi-bell" severity="secondary" [outlined]="true" (onClick)="push.desactivar()" />
        } @else {
          <p-button label="Activar avisos en este dispositivo" icon="pi pi-bell" severity="secondary" (onClick)="push.activar()" />
        }
      }
    </div>
    @if (servicio.items().length) {
      <div class="panel flex flex-col divide-y divide-border overflow-hidden">
        @for (n of servicio.items(); track n.id) {
          <div class="flex items-center gap-3 p-panel">
            <i class="pi" [class]="n.icono" [class.text-fg-muted]="true"></i>
            <span class="flex-1 text-base">{{ n.texto }}</span>
            <span class="flex-none text-xs text-fg-muted">{{ tiempoRelativo(n.fecha) }}</span>
          </div>
        }
      </div>
    } @else {
      <div class="panel flex flex-col items-center gap-2 p-panel py-16 text-center">
        <i class="pi pi-bell text-2xl text-fg-muted"></i>
        <div class="text-base text-fg-muted">No tienes notificaciones todavía.</div>
      </div>
    }
  `,
})
export class NotificacionesComponent {
  protected readonly servicio = inject(NotificacionesService);
  protected readonly push = inject(PushService);
  protected readonly tiempoRelativo = tiempoRelativo;

  // al entrar a esta pagina se dan por leidas -- igual que el modal de la
  // campanita en la app vieja marcaba /notificaciones/leidas al abrirse
  constructor() {
    this.servicio.marcarTodasLeidas();
  }
}
