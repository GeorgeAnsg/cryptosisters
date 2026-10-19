import { Component, computed, inject } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { colorTrader } from '../../shared/utils/color-trader';
import { tiempoRelativo } from '../../shared/utils/tiempo-relativo';
import { CONSENSO_MOCK, fechaGrupo } from '../consenso/consenso-mock';
import { POSICIONES_SPOT_MOCK, POSICIONES_TRADING_MOCK } from '../traders/posiciones/posiciones-mock';
import { SeguidosService } from '../../core/seguidos/seguidos.service';

const LIMITE_RESUMEN = 5;

// Dashboard -- equivalente a renderPaginaPosiciones() en la app vieja (el
// tab se llamaba "Dashboard" en el menu pero la funcion real que pintaba
// era esa, no una pagina nueva). Rejilla de 12 columnas: Consenso reciente
// + Mis posiciones (las dos "cajas negras", fondo panel-dark) arriba, y
// debajo Trading/Spot resumidos (version corta de las tablas de
// Posiciones, limitada a 5 filas cada una, con link "Ver todas").
//
// Simplificado respecto a la app vieja: "Mis posiciones" siempre en su
// estado vacio -- ese es un sistema de copy-trading propio (misPosiciones)
// que este rebuild todavia no tiene montado.
@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [DecimalPipe, RouterLink],
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent {
  protected readonly colorTrader = colorTrader;
  protected readonly tiempoRelativo = tiempoRelativo;
  protected readonly fechaGrupo = fechaGrupo;
  private readonly seguidos = inject(SeguidosService);

  // solo traders que el usuario sigue -- grupos de consenso sin ningun
  // trader seguido desaparecen (no tiene sentido un "consenso" de gente que
  // no sigues)
  protected readonly grupos = computed(() =>
    CONSENSO_MOCK.map((g) => ({ ...g, traders: g.traders.filter((t) => this.seguidos.estaSiguiendo(t.address)) })).filter(
      (g) => g.traders.length > 0,
    ),
  );
  protected readonly resumenTrading = computed(() =>
    POSICIONES_TRADING_MOCK.filter((p) => this.seguidos.estaSiguiendo(p.traderAddress)).slice(0, LIMITE_RESUMEN),
  );
  protected readonly resumenSpot = computed(() =>
    POSICIONES_SPOT_MOCK.filter((p) => this.seguidos.estaSiguiendo(p.traderAddress)).slice(0, LIMITE_RESUMEN),
  );

  protected inicial(nombre: string): string {
    return nombre.charAt(0);
  }
}
