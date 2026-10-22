import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe, DecimalPipe } from '@angular/common';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { Dialog } from 'primeng/dialog';
import { InputNumber } from 'primeng/inputnumber';
import { colorTrader } from '../../../shared/utils/color-trader';
import { MovimientoPosicion, PosicionSpot, PosicionTrading } from './posiciones.model';
import { CandidatosService } from '../../../core/candidatos/candidatos.service';
import { MisPosicionesService } from '../../../core/mis-posiciones/mis-posiciones.service';

interface AberturaPendiente {
  clave: string;
  traderAddress: string;
  tipo: 'trading' | 'spot';
  coin: string;
  lado: string | null;
}

// detalle abierto en el modal movil (mismo objeto que la fila, mas el tipo
// para saber que plantilla de campos mostrar)
interface DetallePosicion {
  tipo: 'trading' | 'spot';
  p: PosicionTrading | PosicionSpot;
}

// "Posiciones" -- lo que tienen abierto AHORA los traders que sigues, no la
// rejilla de descubrimiento (eso es Trading/Spot). Misma idea que
// calcularSeguimiento() en la app vieja: dos tablas, Trading y Spot, cada
// fila desplegable con su historial de movimientos (Abre/Añade/Reduce/
// Cierra) cuando tiene mas de uno. Ver posiciones.model.ts para lo que
// sigue simplificado (consenso, copiar posicion).
@Component({
  selector: 'app-posiciones',
  standalone: true,
  imports: [TableModule, ButtonModule, Dialog, InputNumber, FormsModule, DecimalPipe, DatePipe],
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

  // modal propio (PrimeNG Dialog) para preguntar cuanto invertir al copiar
  // una posicion -- antes era un prompt() nativo del navegador
  protected readonly montoDialogVisible = signal(false);
  protected readonly montoValor = signal<number | null>(null);
  private pendiente: AberturaPendiente | null = null;

  abrirTrading(p: PosicionTrading): void {
    this.pendiente = { clave: this.claveTrading(p), traderAddress: p.traderAddress, tipo: 'trading', coin: p.coin, lado: p.lado };
    this.montoValor.set(null);
    this.montoDialogVisible.set(true);
  }

  abrirSpot(p: PosicionSpot): void {
    this.pendiente = { clave: this.claveSpot(p), traderAddress: p.traderAddress, tipo: 'spot', coin: p.coin, lado: null };
    this.montoValor.set(null);
    this.montoDialogVisible.set(true);
  }

  protected confirmarAbrir(): void {
    if (!this.pendiente) return;
    const { clave, traderAddress, tipo, coin, lado } = this.pendiente;
    this.misPosiciones.abrir(clave, traderAddress, tipo, coin, lado, this.montoValor());
    this.montoDialogVisible.set(false);
    this.pendiente = null;
  }

  // detalle en grande al tocar una tarjeta en movil -- la tabla de
  // escritorio no lo necesita, ya muestra todo en la fila
  protected readonly detalle = signal<DetallePosicion | null>(null);

  abrirDetalle(p: PosicionTrading | PosicionSpot, tipo: 'trading' | 'spot'): void {
    this.detalle.set({ tipo, p });
  }

  protected esTrading(p: PosicionTrading | PosicionSpot): p is PosicionTrading {
    return 'lado' in p;
  }

  protected tituloDetalle(d: DetallePosicion): string {
    return d.tipo === 'trading' ? `${d.p.coin} ${(d.p as PosicionTrading).lado}` : `${d.p.coin} Spot`;
  }

  protected claveDetalle(d: DetallePosicion): string {
    return d.tipo === 'trading' ? this.claveTrading(d.p as PosicionTrading) : this.claveSpot(d.p as PosicionSpot);
  }

  protected abrirDesdeDetalle(d: DetallePosicion): void {
    d.tipo === 'trading' ? this.abrirTrading(d.p as PosicionTrading) : this.abrirSpot(d.p as PosicionSpot);
    this.detalle.set(null);
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
