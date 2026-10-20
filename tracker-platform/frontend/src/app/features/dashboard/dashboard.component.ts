import { Component, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { colorTrader } from '../../shared/utils/color-trader';
import { tiempoRelativo } from '../../shared/utils/tiempo-relativo';
import { fechaGrupo } from '../consenso/consenso.model';
import { CandidatosService } from '../../core/candidatos/candidatos.service';
import { MisPosicionesService } from '../../core/mis-posiciones/mis-posiciones.service';
import { MovimientoPosicion } from '../traders/posiciones/posiciones.model';

const LIMITE_RESUMEN = 5;

// Dashboard -- equivalente a renderPaginaPosiciones() en la app vieja (el
// tab se llamaba "Dashboard" en el menu pero la funcion real que pintaba
// era esa, no una pagina nueva). Rejilla de 12 columnas: Consenso reciente
// + Mis posiciones (las dos "cajas negras", fondo panel-dark) arriba, y
// debajo Trading/Spot resumidos (version corta de las tablas de
// Posiciones, limitada a 5 filas cada una, con link "Ver todas").
@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [DecimalPipe, DatePipe, RouterLink],
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent {
  protected readonly colorTrader = colorTrader;
  protected readonly tiempoRelativo = tiempoRelativo;
  protected readonly fechaGrupo = fechaGrupo;
  private readonly candidatos = inject(CandidatosService);
  private readonly misPosiciones = inject(MisPosicionesService);

  protected readonly grupos = this.candidatos.consensoSeguido;
  protected readonly resumenTrading = computed(() => this.candidatos.posicionesTrading().slice(0, LIMITE_RESUMEN));
  protected readonly resumenSpot = computed(() => this.candidatos.posicionesSpot().slice(0, LIMITE_RESUMEN));
  protected readonly misPosicionesAbiertas = this.misPosiciones.abiertas;

  private readonly nombrePorDireccion = computed(() => {
    const mapa = new Map<string, string>();
    for (const c of this.candidatos.candidatos()) mapa.set(c.address, c.nombre);
    return mapa;
  });

  protected nombreDe(direccion: string): string {
    return this.nombrePorDireccion().get(direccion) ?? `${direccion.slice(0, 8)}…`;
  }

  protected inicial(nombre: string): string {
    return nombre.charAt(0);
  }

  // flechita de detalle, igual que en Posiciones (ver posiciones.component.ts)
  private readonly abiertas = signal<ReadonlySet<string>>(new Set());

  estaAbierta(clave: string): boolean {
    return this.abiertas().has(clave);
  }

  alternarFila(clave: string): void {
    this.abiertas.update((actual) => {
      const siguiente = new Set(actual);
      siguiente.has(clave) ? siguiente.delete(clave) : siguiente.add(clave);
      return siguiente;
    });
  }

  protected movimientosOrdenados(movimientos: MovimientoPosicion[]): MovimientoPosicion[] {
    return [...movimientos].sort((a, b) => b.fecha.localeCompare(a.fecha));
  }
}
