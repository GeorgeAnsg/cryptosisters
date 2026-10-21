import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';
import { Select } from 'primeng/select';
import { InputNumber } from 'primeng/inputnumber';
import { MultiSelect } from 'primeng/multiselect';
import { Popover } from 'primeng/popover';
import { TraderCardComponent } from '../../shared/components/trader-card/trader-card.component';
import { IconButtonComponent } from '../../shared/components/icon-button/icon-button.component';
import { TraderDetailModalComponent } from '../../shared/components/trader-detail-modal/trader-detail-modal.component';
import { PosicionesComponent } from './posiciones/posiciones.component';
import { CribadoComponent } from './cribado/cribado.component';
import { CategoriaMercado, Trader } from '../../shared/models/trader';
import { SeguidosService } from '../../core/seguidos/seguidos.service';
import { Candidato, CandidatosService } from '../../core/candidatos/candidatos.service';

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
  imports: [
    TraderCardComponent,
    IconButtonComponent,
    TraderDetailModalComponent,
    FormsModule,
    Select,
    InputNumber,
    MultiSelect,
    Popover,
    PosicionesComponent,
    CribadoComponent,
  ],
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
  private readonly candidatos = inject(CandidatosService);
  // "siguiendo" se recalcula en cada render a partir de la lista real del
  // usuario (SeguidosService); los traders en si vienen del pool global de
  // descubrimiento (CandidatosService), no de un mock.
  //
  // Trading y Spot son facetas INDEPENDIENTES de un mismo candidato (puede
  // puntuar en una, en la otra, en ambas o en ninguna -- ver
  // descubrimiento.py): igual que la app vieja (index.html, filtroActividad),
  // cada vista solo lista a quien puntua en ESA faceta, y muestra las metricas
  // de esa faceta -- mostrar la puntuacion de trading en la vista Spot (o un
  // candidato sin puntuacion de trading en el listado de Trading) es lo que
  // producia las tarjetas con guiones.
  protected readonly traders = computed<Trader[]>(() => {
    const esSpot = this.vista() === 'spot';
    return this.candidatos
      .candidatos()
      // 'especulativo' (apuesta curada a mano) nunca se juzga por backtest y
      // puede no tener puntuacion de trading -- igual que index.html, solo
      // la vista Trading la deja pasar por ese motivo; Spot exige su propia
      // puntuacion siempre, no hay especulativos de spot
      .filter((c) => (esSpot ? c.puntuacionSpot != null : c.esEspeculativo || c.puntuacion != null))
      .map((c) => ({
        address: c.address,
        nombre: c.nombre,
        esEspeculativo: c.esEspeculativo,
        puntuacion: esSpot ? c.puntuacionSpot : c.puntuacion,
        estilo: c.estilo,
        riesgo: c.riesgo,
        antiguedadDias: c.antiguedadDias ?? 0,
        drawdown: esSpot ? c.drawdownSpot : c.drawdown,
        cuenta: c.cuenta ?? 0,
        winRate: esSpot ? c.winRateSpot : c.winRate,
        retornoPct: esSpot ? c.retornoPctSpot : c.retornoPct,
        profitFactor: esSpot ? c.profitFactorSpot : c.profitFactor,
        monedas: c.monedas,
        desestimado: c.desestimado ?? undefined,
        siguiendo: this.seguidos.estaSiguiendo(c.address),
      }));
  });
  protected readonly retornoMin = signal<number | null>(null);
  protected readonly categoriaFiltro = signal<CategoriaMercado | null>(null);
  // filtro por moneda concreta -- vacio = sin restriccion. Pensado para
  // poder excluir a traders que operan monedas raras/ilíquidas (ej. dejar
  // marcado solo BTC/ETH/SOL/HYPE) sin tener que fiarse solo de la
  // puntuacion, que no dice nada sobre si la moneda es facil de seguir
  protected readonly monedasFiltro = signal<string[]>([]);
  protected readonly opcionesMonedas = computed(() =>
    [...new Set(this.traders().flatMap((t) => t.monedas.map((m) => m.nombre)))].sort().map((nombre) => ({ label: nombre, value: nombre })),
  );
  protected readonly campoOrden = signal<CampoOrden>('puntuacion');
  protected readonly ordenAsc = signal(false);
  // muchos traders comparten nombre de planta (solo hay 40 nombres para
  // 193+ candidatos, ver nombres.py) -- sin esto, encontrar a quien sigues
  // entre varias tarjetas con el mismo nombre es casi imposible a simple
  // vista, aunque el contador de arriba sea correcto
  protected readonly soloSeguidos = signal(false);

  // cuantos filtros (del popover de Filtros) estan activos -- numerito del
  // icono, para saber de un vistazo si hay algo filtrando sin tener que
  // abrir el panel
  protected readonly filtrosActivos = computed(
    () => (this.retornoMin() != null ? 1 : 0) + (this.categoriaFiltro() != null ? 1 : 0) + (this.monedasFiltro().length ? 1 : 0),
  );

  protected readonly tradersFiltrados = computed(() => {
    let lista = this.traders();

    if (this.soloSeguidos()) {
      lista = lista.filter((t) => t.siguiendo);
    }

    const minimo = this.retornoMin();
    if (minimo != null) {
      lista = lista.filter((t) => (t.retornoPct ?? -Infinity) >= minimo);
    }

    const categoria = this.categoriaFiltro();
    if (categoria != null) {
      lista = lista.filter((t) => t.monedas.some((m) => m.categoria === categoria));
    }

    const monedas = this.monedasFiltro();
    if (monedas.length) {
      lista = lista.filter((t) => t.monedas.some((m) => monedas.includes(m.nombre)));
    }

    const campo = this.campoOrden();
    const valorDe = (t: Trader) => (campo === 'retorno' ? t.retornoPct : campo === 'actividad' ? t.antiguedadDias : t.puntuacion);
    const dir = this.ordenAsc() ? 1 : -1;
    // especulativos siempre al final -- no tienen metrica de backtest con
    // la que competir por orden contra el resto (igual que index.html:781);
    // dentro de cada grupo, los que sigues primero (misma razon que arriba)
    return [...lista].sort((a, b) => {
      if (a.esEspeculativo !== b.esEspeculativo) return a.esEspeculativo ? 1 : -1;
      if (a.siguiendo !== b.siguiendo) return a.siguiendo ? -1 : 1;
      return dir * ((valorDe(a) ?? -1) - (valorDe(b) ?? -1));
    });
  });

  protected readonly contadorSiguiendo = computed(() => this.tradersFiltrados().filter((t) => t.siguiendo).length);

  alternarSeguir(trader: Trader, siguiendo: boolean): void {
    this.seguidos.establecer(trader.address, siguiendo);
  }

  // modal de detalle -- igual que abrirModal(c, faceta) en la app vieja: la
  // faceta la decide la pestaña desde la que se tocó la tarjeta (vista())
  protected readonly detalleAbierto = signal(false);
  protected readonly detalleCandidato = signal<Candidato | null>(null);
  protected readonly detalleFaceta = computed<'trading' | 'spot'>(() => (this.vista() === 'spot' ? 'spot' : 'trading'));

  abrirDetalle(trader: Trader): void {
    const candidato = this.candidatos.candidatos().find((c) => c.address === trader.address) ?? null;
    this.detalleCandidato.set(candidato);
    this.detalleAbierto.set(true);
  }
}
