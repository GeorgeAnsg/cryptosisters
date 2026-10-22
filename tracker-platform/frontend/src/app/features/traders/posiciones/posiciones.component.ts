import { Component, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { colorTrader } from '../../../shared/utils/color-trader';
import { DetallePosicionModalComponent } from '../../../shared/components/detalle-posicion-modal/detalle-posicion-modal.component';
import { MovimientoPosicion, PosicionSpot, PosicionTrading } from './posiciones.model';
import { CandidatosService } from '../../../core/candidatos/candidatos.service';
import { MisPosicionesService } from '../../../core/mis-posiciones/mis-posiciones.service';

// "Posiciones" -- lo que tienen abierto AHORA los traders que sigues, no la
// rejilla de descubrimiento (eso es Trading/Spot). Misma idea que
// calcularSeguimiento() en la app vieja: dos tablas, Trading y Spot, cada
// fila desplegable con su historial de movimientos (Abre/Añade/Reduce/
// Cierra) cuando tiene mas de uno. Ver posiciones.model.ts para lo que
// sigue simplificado (consenso, copiar posicion). El modal de detalle/
// copiar vive en DetallePosicionModalComponent (compartido con Dashboard).
@Component({
  selector: 'app-posiciones',
  standalone: true,
  imports: [TableModule, ButtonModule, DatePipe, DecimalPipe, DetallePosicionModalComponent],
  templateUrl: './posiciones.component.html',
})
export class PosicionesComponent {
  protected readonly colorTrader = colorTrader;
  private readonly candidatos = inject(CandidatosService);
  private readonly misPosiciones = inject(MisPosicionesService);

  // solo traders que el usuario sigue -- derivado en CandidatosService
  // (compartido con el resumen del Dashboard) a partir de posicionActual/
  // holdingsSpot de cada candidato seguido, no de un mock.
  protected readonly trading = this.candidatos.posicionesTrading;
  protected readonly spot = this.candidatos.posicionesSpot;

  private readonly abiertas = signal<ReadonlySet<string>>(new Set());

  constructor() {
    this.candidatos.refrescar();
  }

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
    return this.misPosiciones.estaAbierta(clave);
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
