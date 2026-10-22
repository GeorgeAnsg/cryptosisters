import { Component, computed, inject } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { colorTrader } from '../../shared/utils/color-trader';
import { DetalleMiPosicionModalComponent } from '../../shared/components/detalle-mi-posicion-modal/detalle-mi-posicion-modal.component';
import { CandidatosService } from '../../core/candidatos/candidatos.service';
import { MisPosicionesService } from '../../core/mis-posiciones/mis-posiciones.service';

// equivalente a renderPaginaMias() en backend/static/seguimiento.html --
// lo que el usuario mismo ha abierto copiando a alguien que sigue (boton
// Abrir en Posiciones), con detalle de fecha de apertura/cierre y tu
// propio resultado -- distinto del resumen "Mis posiciones" del Dashboard,
// que solo cuenta las abiertas. El modal de detalle (Añadir/Reducir/
// Cerrar) vive en DetalleMiPosicionModalComponent (compartido con Dashboard).
@Component({
  selector: 'app-mis-posiciones',
  standalone: true,
  imports: [TableModule, ButtonModule, DecimalPipe, DatePipe, DetalleMiPosicionModalComponent],
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
}
