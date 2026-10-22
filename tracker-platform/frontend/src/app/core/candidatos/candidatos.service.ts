import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from '../auth/auth.service';
import { MonedaOperada, Estilo, Riesgo } from '../../shared/models/trader';
import { MovimientoPosicion, PosicionSpot, PosicionTrading } from '../../features/traders/posiciones/posiciones.model';
import { GrupoConsenso } from '../../features/consenso/consenso.model';
import { FilaMercadoSpot, FilaMercadoTrading } from '../../features/mercado/mercado.model';
import { agruparEpisodios, construirBloques, FillCrudo, marcarCierres } from '../../shared/utils/episodios';
import { SeguidosService } from '../seguidos/seguidos.service';
import { AjustesService } from '../ajustes/ajustes.service';

export interface PosicionCandidato {
  coin: string;
  lado: 'Long' | 'Short';
  tamaño: number;
  entryPx: number;
  pnlNoRealizado: number;
  valorPosicion: number;
  stopLoss: number | null;
  takeProfit: number | null;
}

export interface HoldingCandidato {
  coin: string;
  tamaño: number;
  costeBase: number | null;
  valorActual: number | null;
  pnlNoRealizado: number | null;
}

export interface Candidato {
  address: string;
  nombre: string;
  esEspeculativo: boolean;
  puntuacion: number | null;
  puntuacionSpot: number | null;
  estilo: Estilo;
  riesgo: Riesgo;
  antiguedadDias: number | null;
  drawdown: number | null;
  cuenta: number | null;
  winRate: number | null;
  retornoPct: number | null;
  profitFactor: number | null;
  drawdownSpot: number | null;
  winRateSpot: number | null;
  retornoPctSpot: number | null;
  profitFactorSpot: number | null;
  monedas: MonedaOperada[];
  desestimado: { motivo: string; fecha: string } | null;
  posicionActual: PosicionCandidato[];
  holdingsSpot: HoldingCandidato[];
  // historial crudo de fills (mas reciente primero) -- ausente en el
  // listado masivo (GET /candidatos, pesaria 20+ MB con 2000 fills x
  // candidato); solo viene relleno al pedir el detalle de UNO
  // (GET /candidatos/{address}, ver cargarDetalle())
  operacionesRecientes?: FillCrudo[];
  movimientosTrading: MovimientoPosicion[];
  movimientosSpot: MovimientoPosicion[];
}

// pool de descubrimiento real (sustituye a TRADERS_MOCK/POSICIONES_*_MOCK/
// CONSENSO_MOCK) -- un solo fetch por sesion de login, igual que
// SeguidosService; Traders/Posiciones/Dashboard/Consenso/Mercado/
// Notificaciones derivan todos de aqui.
@Injectable({ providedIn: 'root' })
export class CandidatosService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly seguidos = inject(SeguidosService);
  private readonly ajustes = inject(AjustesService);

  private readonly lista = signal<readonly Candidato[]>([]);
  private readonly grupos = signal<readonly GrupoConsenso[]>([]);

  constructor() {
    effect(() => {
      const uid = this.auth.uid();
      if (!uid) {
        this.lista.set([]);
        this.grupos.set([]);
        return;
      }
      firstValueFrom(this.http.get<Candidato[]>(`${environment.apiUrl}/candidatos`))
        .then((c) => this.lista.set(c))
        .catch(() => this.lista.set([]));
      firstValueFrom(this.http.get<GrupoConsenso[]>(`${environment.apiUrl}/candidatos/consenso`))
        .then((g) => this.grupos.set(g))
        .catch(() => this.grupos.set([]));
    });
  }

  readonly candidatos = computed(() => this.lista());
  readonly consenso = computed(() => this.grupos());

  // detalle completo (con operacionesRecientes, el historial real de fills)
  // de cada trader SEGUIDO -- el listado masivo no lo trae (pesaria
  // demasiado con 2000 fills x cada uno de los 193+ candidatos), pero el
  // conjunto de seguidos es pequeño, así que aquí sí se puede pedir uno a
  // uno. Esto es lo que permite que Posiciones muestre el mismo historial
  // Abre/Añade/Reduce/Cierra que ya calcula el modal (ver episodios.ts),
  // en vez del recorte sin apenas pasado que daba la tabla "alertas".
  private readonly detallesSeguidos = signal<ReadonlyMap<string, Candidato>>(new Map());
  // direcciones ya pedidas (con exito o no) -- sin esto, una que falla (404,
  // red caida) nunca entra en detallesSeguidos y el effect la vuelve a
  // pedir en cada ciclo porque sigue "faltando", en bucle infinito
  private readonly intentadas = new Set<string>();

  private readonly _cargarDetallesSeguidos = effect(() => {
    const direcciones = this.seguidos.direcciones();
    const faltan = [...direcciones].filter((a) => !this.intentadas.has(a));
    if (!faltan.length) return;
    faltan.forEach((a) => this.intentadas.add(a));
    Promise.all(faltan.map((a) => this.cargarDetalle(a).catch(() => null))).then((detalles) => {
      this.detallesSeguidos.update((mapa) => {
        const nuevo = new Map(mapa);
        detalles.forEach((d: Candidato | null, i: number) => d && nuevo.set(faltan[i], d));
        return nuevo;
      });
    });
  });

  // movimientos reales (fills agrupados en bloques, igual que el modal) de
  // UNA posicion concreta de un trader seguido -- null si aun no hemos
  // pedido su detalle o no tiene historial de fills
  private movimientosReales(traderAddress: string, coin: string, lado: string): MovimientoPosicion[] | null {
    const detalle = this.detallesSeguidos().get(traderAddress);
    if (!detalle?.operacionesRecientes?.length) return null;
    const bloques = construirBloques(agruparEpisodios(detalle.operacionesRecientes));
    const bloque = bloques.find((b) => b.coin === coin && b.lado === lado);
    if (!bloque || bloque.filas.length <= 1) return null;
    return marcarCierres(bloque.filas)
      .map((o) => ({
        fecha: new Date(o.ts).toISOString(),
        verbo:
          lado === 'Spot'
            ? o.accion === 'Abre'
              ? 'Compra'
              : o.cierraDelTodo
                ? 'Cierra'
                : 'Vende'
            : o.accion === 'Abre'
              ? o.esInicio
                ? 'Abre'
                : 'Añade'
              : o.cierraDelTodo
                ? 'Cierra'
                : 'Reduce',
        notionalUsd: o.notional,
        precio: o.px,
        pnlUsd: o.closedPnl || null,
        coin: o.coin,
        lado: lado as MovimientoPosicion['lado'],
      }))
      .reverse(); // mas reciente primero, igual que movimientosTrading/Spot
  }

  // detalle de UN trader, con su historial completo de fills --
  // (operacionesRecientes) para el modal; pedido aparte y a demanda, nunca
  // como parte del listado masivo (ver _candidato_dict en el backend)
  cargarDetalle(address: string): Promise<Candidato> {
    return firstValueFrom(this.http.get<Candidato>(`${environment.apiUrl}/candidatos/${address}`));
  }

  // consenso ya acotado a lo que el usuario sigue -- /candidatos/consenso
  // exige 2+ traders GLOBALMENTE (perspectiva de mercado); tras filtrar por
  // seguidos puede quedar un grupo de 1 o 0, y un grupo de 1 no es consenso
  // (igual que gruposEntrando/gruposCerrando en la app vieja, que ya
  // partian solo de los seguidos). Centralizado aqui porque Dashboard,
  // Consenso y Notificaciones repetian la misma logica.
  readonly consensoSeguido = computed(() =>
    this.grupos()
      .filter((g) => this.ajustes.pasaFiltro(g.coin))
      .map((g) => ({ ...g, traders: g.traders.filter((t) => this.seguidos.estaSiguiendo(t.address)) }))
      .filter((g) => g.traders.length >= 2),
  );

  // mapeo de un candidato a sus filas de Posiciones -- compartido entre
  // posicionesTrading/posicionesSpot (acotados a seguidos)
  private mapTrading(c: Candidato): PosicionTrading[] {
    return c.posicionActual.filter((p) => this.ajustes.pasaFiltro(p.coin)).map((p) => {
      // movimientos reales (fills, con Añade/Reduce de verdad) si ya
      // tenemos el detalle del trader; si no, el recorte de "alertas"
      // (puede estar vacio recien desplegado, ver movimientosTrading)
      const movimientos = this.movimientosReales(c.address, p.coin, p.lado) ?? c.movimientosTrading.filter((m) => m.coin === p.coin && m.lado === p.lado);
      return {
        fecha: movimientos[0]?.fecha ?? new Date().toISOString(),
        lado: p.lado,
        coin: p.coin,
        invertidoUsd: p.valorPosicion,
        cuentaTrader: c.cuenta ?? 0,
        entrada: p.entryPx,
        takeProfit: p.takeProfit,
        stopLoss: p.stopLoss,
        traderAddress: c.address,
        traderNombre: c.nombre,
        resultadoUsd: p.pnlNoRealizado,
        movimientos: movimientos.length > 1 ? movimientos : undefined,
      };
    });
  }

  private mapSpot(c: Candidato): PosicionSpot[] {
    return c.holdingsSpot.filter((h) => this.ajustes.pasaFiltro(h.coin)).map((h) => {
      const movimientos = this.movimientosReales(c.address, h.coin, 'Spot') ?? c.movimientosSpot.filter((m) => m.coin === h.coin);
      return {
        fecha: movimientos[0]?.fecha ?? new Date().toISOString(),
        coin: h.coin,
        invertidoUsd: h.costeBase ?? h.valorActual ?? 0,
        cuentaTrader: c.cuenta ?? 0,
        traderAddress: c.address,
        traderNombre: c.nombre,
        valorActualUsd: h.valorActual ?? 0,
        resultadoUsd: h.pnlNoRealizado,
        movimientos: movimientos.length > 1 ? movimientos : undefined,
      };
    });
  }

  // posiciones ABIERTAS de los traders que el usuario sigue -- lo que
  // alimenta Posiciones y el resumen del Dashboard; derivado una sola vez
  // aqui para no repetir la misma logica en los dos componentes
  readonly posicionesTrading = computed<PosicionTrading[]>(() =>
    this.lista()
      .filter((c) => this.seguidos.estaSiguiendo(c.address))
      .flatMap((c) => this.mapTrading(c))
      // mas reciente primero -- igual que trading.sort(porFecha) en la app
      // vieja, tanto para la tabla como para el recorte a 5 del Dashboard
      .sort((a, b) => b.fecha.localeCompare(a.fecha)),
  );

  readonly posicionesSpot = computed<PosicionSpot[]>(() =>
    this.lista()
      .filter((c) => this.seguidos.estaSiguiendo(c.address))
      .flatMap((c) => this.mapSpot(c))
      .sort((a, b) => b.fecha.localeCompare(a.fecha)),
  );

  // percepcion de mercado -- agregado sobre TODOS los candidatos (no solo
  // a quien sigues, a diferencia de posicionesTrading/posicionesSpot).
  // MERCADO_MINIMO_USD descarta polvo/airdrops ($ < 1000) antes de agregar
  // -- igual que calcularMercado() en la app vieja; sin esto, una posicion
  // de $10 cuenta igual que una de $50k en el reparto long/short.
  readonly mercadoTrading = computed<FilaMercadoTrading[]>(() => {
    const porCoin = new Map<string, FilaMercadoTrading>();
    for (const c of this.lista()) {
      for (const p of c.posicionActual) {
        if (p.valorPosicion < MERCADO_MINIMO_USD) continue;
        const fila = porCoin.get(p.coin) ?? { coin: p.coin, nLong: 0, nShort: 0, dLong: 0, dShort: 0 };
        if (p.lado === 'Long') {
          fila.nLong++;
          fila.dLong += p.valorPosicion;
        } else {
          fila.nShort++;
          fila.dShort += p.valorPosicion;
        }
        porCoin.set(p.coin, fila);
      }
    }
    return [...porCoin.values()];
  });

  readonly mercadoSpot = computed<FilaMercadoSpot[]>(() => {
    const porCoin = new Map<string, FilaMercadoSpot>();
    for (const c of this.lista()) {
      for (const h of c.holdingsSpot) {
        if ((h.valorActual ?? 0) < MERCADO_MINIMO_USD) continue;
        const fila = porCoin.get(h.coin) ?? { coin: h.coin, n: 0, d: 0 };
        fila.n++;
        fila.d += h.valorActual ?? 0;
        porCoin.set(h.coin, fila);
      }
    }
    return [...porCoin.values()];
  });
}

const MERCADO_MINIMO_USD = 1000;
