import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';
import { Select } from 'primeng/select';
import { InputNumber } from 'primeng/inputnumber';
import { TraderCardComponent } from '../../shared/components/trader-card/trader-card.component';
import { IconButtonComponent } from '../../shared/components/icon-button/icon-button.component';
import { PosicionesComponent } from './posiciones/posiciones.component';
import { CribadoComponent } from './cribado/cribado.component';
import { CategoriaMercado, Trader } from '../../shared/models/trader';
import { TRADERS_MOCK } from './mock-traders';
import { SeguidosService } from '../../core/seguidos/seguidos.service';

type CampoOrden = 'puntuacion' | 'retorno' | 'actividad';
type Vista = 'trading' | 'spot' | 'posiciones' | 'cribado';

const CATEGORIAS: { label: string; value: CategoriaMercado | null }[] = [
  { label: 'Todas las categorías', value: null },
  { label: 'Cripto', value: 'Cripto' },
  { label: 'Acción', value: 'Acción' },
  { label: 'Materia prima', value: 'Materia prima' },
  { label: 'Divisa', value: 'Divisa' },
  { label: 'Índice', value: 'Índice' },
];
const CAMPOS_ORDEN: { label: string; value: CampoOrden }[] = [
  { label: 'Puntuación', value: 'puntuacion' },
  { label: 'Retorno', value: 'retorno' },
  { label: 'Actividad reciente', value: 'actividad' },
];

// pestaña Traders -- misma estructura que renderPaginaSeguimiento() en la
// app vieja (backend/static/index.html): un solo componente que cambia de
// contenido segun subVistaTraders/vista, con el submenu ahora en el sidebar
// en vez de pestañas dentro de la pagina. Trading/Spot comparten la misma
// rejilla de tarjetas (con datos de mentira, TRADERS_MOCK, por ahora);
// Posiciones y Cribado son componentes propios, bastante distintos en
// forma (tabla / fichas de solo lectura) como para no forzarlos aqui dentro.
@Component({
  selector: 'app-traders',
  standalone: true,
  imports: [TraderCardComponent, IconButtonComponent, FormsModule, Select, InputNumber, PosicionesComponent, CribadoComponent],
  templateUrl: './traders.component.html',
})
export class TradersComponent {
  private readonly route = inject(ActivatedRoute);

  protected readonly categorias = CATEGORIAS;
  protected readonly camposOrden = CAMPOS_ORDEN;

  protected readonly vista = toSignal(this.route.queryParamMap.pipe(map((params) => (params.get('vista') as Vista) ?? 'trading')), {
    initialValue: 'trading' as Vista,
  });

  protected readonly titulo = computed(() => (this.vista() === 'spot' ? 'Listado de billeteras spot' : 'Listado de traders'));

  // la URL siempre lleva ?vista= para que el sidebar resalte el item
  // correcto al entrar directamente en /traders sin query param
  constructor() {
    const router = inject(Router);
    if (!this.route.snapshot.queryParamMap.has('vista')) {
      router.navigate([], { relativeTo: this.route, queryParams: { vista: 'trading' }, replaceUrl: true });
    }
  }

  private readonly seguidos = inject(SeguidosService);
  // "siguiendo" ya no es un campo fijo del mock -- se recalcula en cada
  // render a partir de la lista real del usuario (SeguidosService)
  protected readonly traders = computed<Trader[]>(() =>
    TRADERS_MOCK.map((t) => ({ ...t, siguiendo: this.seguidos.estaSiguiendo(t.address) })),
  );
  protected readonly retornoMin = signal<number | null>(null);
  protected readonly categoriaFiltro = signal<CategoriaMercado | null>(null);
  protected readonly campoOrden = signal<CampoOrden>('puntuacion');
  protected readonly ordenAsc = signal(false);

  protected readonly tradersFiltrados = computed(() => {
    let lista = this.traders();

    const minimo = this.retornoMin();
    if (minimo != null) {
      lista = lista.filter((t) => (t.retornoPct ?? -Infinity) >= minimo);
    }

    const categoria = this.categoriaFiltro();
    if (categoria != null) {
      lista = lista.filter((t) => t.monedas.some((m) => m.categoria === categoria));
    }

    const campo = this.campoOrden();
    const valorDe = (t: Trader) => (campo === 'retorno' ? t.retornoPct : campo === 'actividad' ? t.antiguedadDias : t.puntuacion);
    const dir = this.ordenAsc() ? 1 : -1;
    return [...lista].sort((a, b) => dir * ((valorDe(a) ?? -1) - (valorDe(b) ?? -1)));
  });

  protected readonly contadorSiguiendo = computed(() => this.tradersFiltrados().filter((t) => t.siguiendo).length);

  alternarSeguir(trader: Trader, siguiendo: boolean): void {
    this.seguidos.establecer(trader.address, siguiendo);
  }
}
