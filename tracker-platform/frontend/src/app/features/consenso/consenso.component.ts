import { Component, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { ButtonModule } from 'primeng/button';
import { colorTrader } from '../../shared/utils/color-trader';
import { tiempoRelativo } from '../../shared/utils/tiempo-relativo';
import { CONSENSO_MOCK, ConsensoTrader, fechaGrupo } from './consenso-mock';
import { SeguidosService } from '../../core/seguidos/seguidos.service';

// "Consenso" -- equivalente a renderPaginaConsenso() en la app vieja:
// la version expandida de la misma caja negra que aparece resumida
// (en chips) en el Dashboard, aqui con una fila por trader (orden: quien
// entro/cerro antes primero) y su detalle (tamaño, precio).
@Component({
  selector: 'app-consenso',
  standalone: true,
  imports: [DecimalPipe, ButtonModule],
  templateUrl: './consenso.component.html',
})
export class ConsensoComponent {
  protected readonly colorTrader = colorTrader;
  protected readonly tiempoRelativo = tiempoRelativo;
  protected readonly fechaGrupo = fechaGrupo;
  private readonly seguidos = inject(SeguidosService);

  protected readonly grupos = computed(() =>
    CONSENSO_MOCK.map((g) => ({ ...g, traders: g.traders.filter((t) => this.seguidos.estaSiguiendo(t.address)) })).filter(
      (g) => g.traders.length > 0,
    ),
  );

  // igual que en Posiciones -- "Abrir" copia la jugada a "mis posiciones",
  // sistema que este rebuild todavia no tiene; de momento solo marca el
  // boton como abierto en esta sesion
  private readonly copiadas = signal<ReadonlySet<string>>(new Set());

  protected inicial(nombre: string): string {
    return nombre.charAt(0);
  }

  // quien entro/cerro antes primero
  protected ordenados(traders: ConsensoTrader[]): ConsensoTrader[] {
    return [...traders].sort((a, b) => a.fecha.localeCompare(b.fecha));
  }

  protected clave(coin: string, lado: string, address: string): string {
    return `${coin}_${lado}_${address}`;
  }

  protected estaCopiada(clave: string): boolean {
    return this.copiadas().has(clave);
  }

  protected abrirPosicion(clave: string): void {
    this.copiadas.update((actual) => new Set(actual).add(clave));
  }
}
