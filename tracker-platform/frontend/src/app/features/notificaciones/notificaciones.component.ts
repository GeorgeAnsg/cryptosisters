import { Component, inject } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { Button } from 'primeng/button';
import { NotificacionesService } from '../../core/notificaciones/notificaciones.service';
import { PushService } from '../../core/push/push.service';
import { CandidatosService } from '../../core/candidatos/candidatos.service';
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
  private readonly candidatos = inject(CandidatosService);
  protected readonly tiempoRelativo = tiempoRelativo;
  protected readonly colorTrader = colorTrader;

  // al entrar a esta pagina se dan por leidas -- igual que el modal de la
  // campanita en la app vieja marcaba /notificaciones/leidas al abrirse.
  // Tambien se refresca aqui: antes solo se pedia una vez al iniciar
  // sesion, asi que una notificacion push recien llegada nunca aparecia
  // sin recargar toda la app.
  constructor() {
    this.servicio.marcarTodasLeidas();
    this.candidatos.refrescar();
  }
}
