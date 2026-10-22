import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe, DecimalPipe } from '@angular/common';
import { ButtonModule } from 'primeng/button';
import { Dialog } from 'primeng/dialog';
import { InputNumber } from 'primeng/inputnumber';
import { colorTrader } from '../../utils/color-trader';
import { MovimientoPosicion, PosicionSpot, PosicionTrading } from '../../../features/traders/posiciones/posiciones.model';
import { MisPosicionesService } from '../../../core/mis-posiciones/mis-posiciones.service';

interface AberturaPendiente {
  clave: string;
  traderAddress: string;
  tipo: 'trading' | 'spot';
  coin: string;
  lado: string | null;
}

interface DetallePosicion {
  tipo: 'trading' | 'spot';
  p: PosicionTrading | PosicionSpot;
}

// detalle de la posicion de OTRO trader (Posiciones) + el dialogo de "cuanto
// invertir" para copiarla -- extraido de PosicionesComponent para poder
// abrirlo tambien desde el Dashboard (misma tarjeta, mismo modal, no una
// copia con otro aspecto)
@Component({
  selector: 'app-detalle-posicion-modal',
  standalone: true,
  imports: [ButtonModule, Dialog, InputNumber, FormsModule, DecimalPipe, DatePipe],
  templateUrl: './detalle-posicion-modal.component.html',
})
export class DetallePosicionModalComponent {
  protected readonly colorTrader = colorTrader;
  private readonly misPosiciones = inject(MisPosicionesService);

  protected readonly detalle = signal<DetallePosicion | null>(null);
  protected readonly montoDialogVisible = signal(false);
  protected readonly montoValor = signal<number | null>(null);
  private pendiente: AberturaPendiente | null = null;

  claveTrading(p: PosicionTrading): string {
    return `t_${p.traderAddress}_${p.coin}_${p.lado}`;
  }

  claveSpot(p: PosicionSpot): string {
    return `s_${p.traderAddress}_${p.coin}`;
  }

  estaCopiada(clave: string): boolean {
    return this.misPosiciones.estaAbierta(clave);
  }

  abrirDetalle(p: PosicionTrading | PosicionSpot, tipo: 'trading' | 'spot'): void {
    this.detalle.set({ tipo, p });
  }

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

  protected movimientosOrdenados(movimientos: MovimientoPosicion[]): MovimientoPosicion[] {
    return [...movimientos].sort((a, b) => b.fecha.localeCompare(a.fecha));
  }
}
