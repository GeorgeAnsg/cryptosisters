import { Injectable, computed, inject, signal } from '@angular/core';
import { CONSENSO_MOCK } from '../../features/consenso/consenso-mock';
import { POSICIONES_SPOT_MOCK, POSICIONES_TRADING_MOCK } from '../../features/traders/posiciones/posiciones-mock';
import { TRADERS_MOCK } from '../../features/traders/mock-traders';
import { SeguidosService } from '../seguidos/seguidos.service';

export interface NotificacionItem {
  id: string;
  fecha: string;
  icono: string;
  texto: string;
}

// verbo de un movimiento (ver posiciones-mock.ts) -> accion en pasado para
// el texto de la notificacion
const ACCION_TRADING: Record<string, string> = {
  'Abre (inicio)': 'abrió',
  Añade: 'añadió a',
  Reduce: 'redujo',
  Cierra: 'cerró',
};
const ACCION_SPOT: Record<string, string> = {
  'Compra (inicio)': 'compró',
  Compra: 'compró más',
  Vende: 'vendió',
  Cierra: 'cerró',
};

// Notificaciones -- basado en los disparadores reales que tenia la app
// vieja (crear_notificacion en refresher.py/descubrimiento.py), menos el
// resumen semanal de descubrimiento completo (decision explicita: no
// interesa salvo que aparezca alguien "subrumal top", eso se aparca para
// mas adelante). AHORA todo filtrado por usuario (la app vieja no tenia
// usuarios, era un unico feed global); el pool de descubrimiento en si
// sigue siendo global para toda la plataforma (TRADERS_MOCK), solo la
// notificacion es personal:
//   1. Consenso nuevo entre traders que sigues (detectar_consenso)
//   2. Un trader que sigues abre/añade/reduce/cierra trading, o
//      compra/vende en spot (detectar_alertas -- en la app vieja esto solo
//      alimentaba la tabla de alertas, nunca notificaba; aqui si, porque
//      ahora es TU lista personal de traders, no el pool entero)
//   3. Un trader que sigues es desestimado del pool de descubrimiento (ya
//      no pasa el filtro de calidad) -- antes iba dentro del resumen
//      semanal global, ahora es un aviso personal solo si te afecta a ti
//
// Derivadas de los mocks por ahora -- el backend real de consenso/alertas/
// descubrimiento todavia no esta portado, asi que no hay un "evento nuevo"
// real que detectar; en cuanto exista, esto se sustituye por una lista que
// venga del backend en vez de recalcularse aqui.
@Injectable({ providedIn: 'root' })
export class NotificacionesService {
  private readonly seguidos = inject(SeguidosService);
  private readonly leidas = signal<ReadonlySet<string>>(new Set());

  readonly items = computed<NotificacionItem[]>(() => {
    const seguido = (addr: string) => this.seguidos.estaSiguiendo(addr);

    const deConsenso: NotificacionItem[] = CONSENSO_MOCK.map((g) => ({ ...g, traders: g.traders.filter((t) => seguido(t.address)) }))
      .filter((g) => g.traders.length > 0)
      .map((g) => ({
        id: `consenso_${g.coin}_${g.lado}`,
        fecha: g.traders.map((t) => t.fecha).sort().at(-1)!,
        icono: 'pi-bolt',
        texto: `Consenso: ${g.traders.length} traders ${g.lado} ${g.verbo} en ${g.coin}`,
      }));

    const deTrading: NotificacionItem[] = POSICIONES_TRADING_MOCK.filter((p) => seguido(p.traderAddress)).flatMap((p) =>
      (p.movimientos ?? [{ fecha: p.fecha, verbo: 'Abre (inicio)', notionalUsd: p.invertidoUsd, precio: p.entrada, pnlUsd: null }]).map(
        (m, i) => ({
          id: `trading_${p.traderAddress}_${p.coin}_${i}`,
          fecha: m.fecha,
          icono: 'pi-chart-line',
          texto: `${p.traderNombre} ${ACCION_TRADING[m.verbo] ?? m.verbo} ${p.lado} en ${p.coin}`,
        }),
      ),
    );

    const deSpot: NotificacionItem[] = POSICIONES_SPOT_MOCK.filter((p) => seguido(p.traderAddress)).flatMap((p) =>
      (p.movimientos ?? [{ fecha: p.fecha, verbo: 'Compra (inicio)', notionalUsd: p.invertidoUsd, precio: 0, pnlUsd: null }]).map(
        (m, i) => ({
          id: `spot_${p.traderAddress}_${p.coin}_${i}`,
          fecha: m.fecha,
          icono: 'pi-wallet',
          texto: `${p.traderNombre} ${ACCION_SPOT[m.verbo] ?? m.verbo} ${p.coin} en spot`,
        }),
      ),
    );

    const deDesestimados: NotificacionItem[] = TRADERS_MOCK.filter((t) => seguido(t.address) && t.desestimado).map((t) => ({
      id: `desestimado_${t.address}`,
      fecha: t.desestimado!.fecha,
      icono: 'pi-user-minus',
      texto: `${t.nombre} ha sido desestimado del descubrimiento (${t.desestimado!.motivo}) -- has perdido esa posición`,
    }));

    return [...deConsenso, ...deTrading, ...deSpot, ...deDesestimados].sort((a, b) => b.fecha.localeCompare(a.fecha));
  });

  readonly hayNoLeidas = computed(() => this.items().some((n) => !this.leidas().has(n.id)));

  marcarTodasLeidas(): void {
    this.leidas.set(new Set(this.items().map((n) => n.id)));
  }
}
