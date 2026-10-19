import { Component, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { colorTrader } from '../../../shared/utils/color-trader';
import { MovimientoPosicion, POSICIONES_SPOT_MOCK, POSICIONES_TRADING_MOCK, PosicionSpot, PosicionTrading } from './posiciones-mock';
import { SeguidosService } from '../../../core/seguidos/seguidos.service';

// "Posiciones" -- lo que tienen abierto AHORA los traders que sigues, no la
// rejilla de descubrimiento (eso es Trading/Spot). Misma idea que
// calcularSeguimiento() en la app vieja: dos tablas, Trading y Spot, cada
// fila desplegable con su historial de movimientos (Abre/Añade/Reduce/
// Cierra) cuando tiene mas de uno. Ver posiciones-mock.ts para lo que
// sigue simplificado (consenso, copiar posicion).
@Component({
  selector: 'app-posiciones',
  standalone: true,
  imports: [TableModule, ButtonModule, DecimalPipe, DatePipe],
  templateUrl: './posiciones.component.html',
})
export class PosicionesComponent {
  protected readonly colorTrader = colorTrader;
  private readonly seguidos = inject(SeguidosService);
  // solo traders que el usuario sigue -- un usuario que no sigue a nadie no
  // debe ver ninguna posicion de nadie
  protected readonly trading = computed(() => POSICIONES_TRADING_MOCK.filter((p) => this.seguidos.estaSiguiendo(p.traderAddress)));
  protected readonly spot = computed(() => POSICIONES_SPOT_MOCK.filter((p) => this.seguidos.estaSiguiendo(p.traderAddress)));

  private readonly abiertas = signal<ReadonlySet<string>>(new Set());
  // posiciones que el usuario ya ha copiado a "mis posiciones" -- de
  // momento solo marca el boton como abierto en esta sesion (no persiste,
  // no hay backend de copy-trading todavia), pero al menos "Abrir" hace
  // algo visible en vez de no reaccionar
  private readonly copiadas = signal<ReadonlySet<string>>(new Set());

  claveTrading(p: PosicionTrading): string {
    return `t_${p.traderAddress}_${p.coin}_${p.lado}`;
  }

  claveSpot(p: PosicionSpot): string {
    return `s_${p.traderAddress}_${p.coin}`;
  }

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

  estaCopiada(clave: string): boolean {
    return this.copiadas().has(clave);
  }

  abrirPosicion(clave: string): void {
    this.copiadas.update((actual) => new Set(actual).add(clave));
  }

  protected pctCartera(invertido: number, cuenta: number): string {
    return cuenta ? `${((invertido / cuenta) * 100).toFixed(1)}%` : '—';
  }

  protected inicial(nombre: string): string {
    return nombre.charAt(0);
  }

  // mas reciente arriba, la apertura (el mas antiguo) al final -- igual que
  // la app vieja (marcarCierres(filasReales).reverse())
  protected movimientosOrdenados(movimientos: MovimientoPosicion[]): MovimientoPosicion[] {
    return [...movimientos].sort((a, b) => b.fecha.localeCompare(a.fecha));
  }
}
