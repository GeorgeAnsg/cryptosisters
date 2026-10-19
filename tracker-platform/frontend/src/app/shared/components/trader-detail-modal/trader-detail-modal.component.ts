import { Component, computed, effect, inject, input, model, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { Dialog } from 'primeng/dialog';
import { TableModule } from 'primeng/table';
import { colorTrader } from '../../utils/color-trader';
import { Candidato, CandidatosService } from '../../../core/candidatos/candidatos.service';
import { Bloque, FilaConCierre, agruparEpisodios, construirBloques, marcarCierres } from '../../utils/episodios';

export type Faceta = 'trading' | 'spot';

interface BloqueVista {
  bloque: Bloque;
  tamanoCabecera: number;
  tituloTamano: string;
  fecha: string;
  pnl: { valor: number | null; realizado: boolean };
  hijos: FilaConCierre[];
}

// equivalente a abrirModal(c, faceta) en backend/static/index.html --
// detalle de UN trader en UNA faceta (nunca pestañas para cambiar: un
// trader de Spot es de Spot, uno de Trading es de Trading). Reconstruye
// bloques/episodios a partir de operacionesRecientes (fills crudos), igual
// que agruparEpisodios/construirBloques/renderBloques en la app vieja --
// NO usa posicionActual/holdingsSpot mas que para el dato EN VIVO (pnl y
// tamaño de lo que sigue abierto), igual que alli.
@Component({
  selector: 'app-trader-detail-modal',
  standalone: true,
  imports: [Dialog, TableModule, DecimalPipe, DatePipe],
  templateUrl: './trader-detail-modal.component.html',
})
export class TraderDetailModalComponent {
  private readonly candidatosSrv = inject(CandidatosService);

  // candidato "ligero" (el que ya tiene la lista general, sin
  // operacionesRecientes -- ver candidatos.service.ts); al abrirse se pide
  // el detalle completo aparte, un trader a la vez, para no tener que
  // cargar el historial de fills de TODOS los candidatos de golpe
  candidato = input<Candidato | null>(null);
  faceta = input<Faceta>('trading');
  visible = model(false);

  protected readonly colorTrader = colorTrader;
  protected readonly cargando = signal(false);
  private readonly detalle = signal<Candidato | null>(null);

  constructor() {
    effect(() => {
      const c = this.candidato();
      if (!this.visible() || !c) {
        return;
      }
      this.cargando.set(true);
      this.detalle.set(null);
      this.candidatosSrv
        .cargarDetalle(c.address)
        .then((d) => this.detalle.set(d))
        .catch(() => this.detalle.set(c)) // sin historial de fills, pero al menos holdingsSpot/posicionActual en vivo
        .finally(() => this.cargando.set(false));
    });
  }

  private readonly bloques = computed<Bloque[]>(() => {
    const c = this.detalle();
    if (!c) return [];
    return construirBloques(agruparEpisodios(c.operacionesRecientes ?? []));
  });

  // live: posicion/holding en vivo para una posicion que sigue abierta --
  // mismo dato que pinta Traders, aqui solo para pnl/tamaño de cabecera
  private pnlEnVivoPerp(coin: string, lado: string): number | null {
    const c = this.detalle();
    const p = c?.posicionActual.find((x) => x.coin === coin && x.lado === lado);
    return p ? p.pnlNoRealizado : null;
  }

  private tamañoEnVivoPerp(coin: string, lado: string): number | null {
    const c = this.detalle();
    const p = c?.posicionActual.find((x) => x.coin === coin && x.lado === lado);
    return p ? p.tamaño * p.entryPx : null;
  }

  // ordenadas: abiertas siempre primero (da igual la fecha de su ultimo
  // movimiento), despues cerradas de mas reciente a mas antigua -- igual
  // que renderBloques() en la app vieja
  private ordenarBloques(lista: Bloque[]): Bloque[] {
    return [...lista].sort((a, b) => (b.abierta ? 1 : 0) - (a.abierta ? 1 : 0));
  }

  protected readonly bloquesTrading = computed<BloqueVista[]>(() =>
    this.ordenarBloques(this.bloques().filter((b) => b.lado === 'Long' || b.lado === 'Short')).map((b) => this.vistaDeBloque(b)),
  );

  private vistaDeBloque(b: Bloque): BloqueVista {
    const ultima = b.filas[b.filas.length - 1];
    let tamanoCabecera: number;
    let tituloTamano: string;
    let pnl: { valor: number | null; realizado: boolean };
    if (b.abierta) {
      const vivo = this.tamañoEnVivoPerp(b.coin, b.lado);
      tamanoCabecera = vivo ?? b.filas.reduce((a, o) => a + (o.accion === 'Abre' ? o.notional || 0 : -(o.notional || 0)), 0);
      tituloTamano = 'Lo invertido ahora mismo en esta posición (precio de entrada × tamaño en vivo)';
      pnl = { valor: this.pnlEnVivoPerp(b.coin, b.lado), realizado: false };
    } else {
      tamanoCabecera = b.filas.filter((o) => o.accion === 'Abre').reduce((a, o) => a + (o.notional || 0), 0);
      tituloTamano = 'Total invertido en esta posición a lo largo de todo el historial visible';
      const pnlRealizado = b.filas.reduce((a, o) => a + (o.closedPnl || 0), 0);
      pnl = { valor: pnlRealizado || null, realizado: true };
    }
    return {
      bloque: b,
      tamanoCabecera,
      tituloTamano,
      fecha: new Date(ultima.ts).toISOString(),
      pnl,
      // hijos solo si hay mas de un episodio -- igual que la flechita ▸ en
      // la app vieja (b.filas.length > 1)
      hijos: b.filas.length > 1 ? marcarCierres(b.filas).reverse() : [],
    };
  }

  // spot NO agrupa por bloque en pantalla (eso duplicaria el dato EN VIVO
  // de holdingsSpot) -- listado plano de todas las compras/ventas, la mas
  // reciente primero
  protected readonly movimientosSpot = computed<FilaConCierre[]>(() =>
    this.bloques()
      .filter((b) => b.lado === 'Spot')
      .flatMap((b) => marcarCierres(b.filas))
      .sort((a, b) => b.ts - a.ts),
  );

  protected readonly holdingsSpot = computed(() => this.detalle()?.holdingsSpot ?? []);
  protected readonly totalOperaciones = computed<number | null>(() => this.detalle()?.operacionesRecientes?.length ?? null);

  private readonly abiertas = signal<ReadonlySet<string>>(new Set());

  protected direccionCorta(c: Candidato): string {
    return `${c.address.slice(0, 8)}…${c.address.slice(-4)}`;
  }

  protected clave(coin: string, lado: string): string {
    return `${coin}|${lado}`;
  }

  protected estaAbierta(clave: string): boolean {
    return this.abiertas().has(clave);
  }

  protected alternarFila(clave: string): void {
    this.abiertas.update((actual) => {
      const siguiente = new Set(actual);
      siguiente.has(clave) ? siguiente.delete(clave) : siguiente.add(clave);
      return siguiente;
    });
  }

  protected verboHijo(o: FilaConCierre): string {
    return o.accion === 'Abre' ? 'Añade' : o.cierraDelTodo ? 'Cierra' : 'Reduce';
  }

  protected verboSpot(o: FilaConCierre): string {
    return o.accion === 'Abre' ? 'Compra' : o.cierraDelTodo ? 'Cierra' : 'Vende';
  }
}
