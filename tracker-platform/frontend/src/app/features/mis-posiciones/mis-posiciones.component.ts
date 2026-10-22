import { Component, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { Dialog } from 'primeng/dialog';
import { colorTrader } from '../../shared/utils/color-trader';
import { CandidatosService } from '../../core/candidatos/candidatos.service';
import { MiPosicion, MisPosicionesService } from '../../core/mis-posiciones/mis-posiciones.service';

// equivalente a renderPaginaMias() en backend/static/seguimiento.html --
// lo que el usuario mismo ha abierto copiando a alguien que sigue (boton
// Abrir en Posiciones), con detalle de fecha de apertura/cierre y tu
// propio resultado -- distinto del resumen "Mis posiciones" del Dashboard,
// que solo cuenta las abiertas.
@Component({
  selector: 'app-mis-posiciones',
  standalone: true,
  imports: [TableModule, ButtonModule, Dialog, DecimalPipe, DatePipe],
  templateUrl: './mis-posiciones.component.html',
})
export class MisPosicionesComponent {
  protected readonly colorTrader = colorTrader;
  private readonly candidatos = inject(CandidatosService);
  private readonly misPosiciones = inject(MisPosicionesService);

  protected readonly abiertas = this.misPosiciones.abiertas;
  protected readonly cerradas = this.misPosiciones.cerradas;

  constructor() {
    this.candidatos.refrescar();
    this.misPosiciones.refrescar();
  }

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

  // detalle en grande al tocar una tarjeta en movil -- mismos botones que
  // la fila de la tabla de escritorio
  protected readonly detalle = signal<MiPosicion | null>(null);

  protected abrirDetalle(m: MiPosicion): void {
    this.detalle.set(m);
  }

  protected cerrar(clave: string, coin: string): void {
    const texto = prompt(`¿Cuánto has ganado o perdido cerrando ${coin}? (en $, negativo si has perdido)`);
    if (texto === null) return;
    const pnl = parseFloat(texto.replace(',', '.'));
    if (isNaN(pnl)) {
      alert('Eso no es un número.');
      return;
    }
    this.misPosiciones.cerrar(clave, pnl);
  }

  // Añadir/Reducir -- mismo patron que Cerrar (prompt con el monto a mano,
  // el usuario copia lo que ve que hace el trader, no se infiere solo)
  protected ajustar(clave: string, coin: string, signo: 1 | -1): void {
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
