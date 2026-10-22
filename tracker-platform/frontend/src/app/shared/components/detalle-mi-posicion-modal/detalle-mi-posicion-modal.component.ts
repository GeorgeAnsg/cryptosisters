import { Component, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { ButtonModule } from 'primeng/button';
import { Dialog } from 'primeng/dialog';
import { colorTrader } from '../../utils/color-trader';
import { CandidatosService } from '../../../core/candidatos/candidatos.service';
import { MiPosicion, MisPosicionesService } from '../../../core/mis-posiciones/mis-posiciones.service';

// detalle de una posicion MIA (Mis Posiciones) -- extraido de
// MisPosicionesComponent para poder abrirlo tambien desde el Dashboard,
// con el mismo modal (Añadir/Reducir/Cerrar) en vez de una copia aparte
@Component({
  selector: 'app-detalle-mi-posicion-modal',
  standalone: true,
  imports: [ButtonModule, Dialog, DecimalPipe, DatePipe],
  templateUrl: './detalle-mi-posicion-modal.component.html',
})
export class DetalleMiPosicionModalComponent {
  protected readonly colorTrader = colorTrader;
  private readonly candidatos = inject(CandidatosService);
  private readonly misPosiciones = inject(MisPosicionesService);

  protected readonly detalle = signal<MiPosicion | null>(null);

  private readonly nombrePorDireccion = computed(() => {
    const mapa = new Map<string, string>();
    for (const c of this.candidatos.candidatos()) mapa.set(c.address, c.nombre);
    return mapa;
  });

  protected nombreDe(direccion: string): string {
    return this.nombrePorDireccion().get(direccion) ?? `${direccion.slice(0, 8)}…`;
  }

  protected readonly pctEnVivo = this.misPosiciones.pctEnVivo.bind(this.misPosiciones);
  protected readonly usdEnVivo = this.misPosiciones.usdEnVivo.bind(this.misPosiciones);
  protected readonly traderCerro = this.misPosiciones.traderCerro.bind(this.misPosiciones);

  abrirDetalle(m: MiPosicion): void {
    this.detalle.set(m);
  }

  // publicos (no protected): la tabla de escritorio de MisPosicionesComponent
  // tambien los llama, via la referencia de plantilla #modal
  cerrar(clave: string, coin: string): void {
    const texto = prompt(`¿Cuánto has ganado o perdido cerrando ${coin}? (en $, negativo si has perdido)`);
    if (texto === null) return;
    const pnl = parseFloat(texto.replace(',', '.'));
    if (isNaN(pnl)) {
      alert('Eso no es un número.');
      return;
    }
    this.misPosiciones.cerrar(clave, pnl);
  }

  ajustar(clave: string, coin: string, signo: 1 | -1): void {
    const verbo = signo > 0 ? 'añadir' : 'reducir';
    const texto = prompt(`¿Cuántos $ quieres ${verbo} en ${coin}?`);
    if (texto === null) return;
    const monto = parseFloat(texto.replace(',', '.'));
    if (isNaN(monto) || monto < 0) {
      alert('Eso no es un número.');
      return;
    }
    this.misPosiciones.ajustar(clave, signo * monto);
  }
}
