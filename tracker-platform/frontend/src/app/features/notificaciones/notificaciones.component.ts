import { Component, inject } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { Button } from 'primeng/button';
import { NotificacionesService } from '../../core/notificaciones/notificaciones.service';
import { PushService } from '../../core/push/push.service';
import { colorTrader } from '../../shared/utils/color-trader';
import { tiempoRelativo } from '../../shared/utils/tiempo-relativo';

@Component({
  selector: 'app-notificaciones',
  standalone: true,
  imports: [Button, DecimalPipe],
  templateUrl: './notificaciones.component.html',
})
export class NotificacionesComponent {
  protected readonly servicio = inject(NotificacionesService);
  protected readonly push = inject(PushService);
  protected readonly tiempoRelativo = tiempoRelativo;
  protected readonly colorTrader = colorTrader;

  // al entrar a esta pagina se dan por leidas -- igual que el modal de la
  // campanita en la app vieja marcaba /notificaciones/leidas al abrirse
  constructor() {
    this.servicio.marcarTodasLeidas();
  }
}
