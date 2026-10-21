import { Injectable, computed, inject, signal } from '@angular/core';
import { CandidatosService } from '../candidatos/candidatos.service';
import { SeguidosService } from '../seguidos/seguidos.service';

export type TipoNotificacion = 'trading' | 'spot' | 'consenso' | 'desestimado';

export interface NotificacionItem {
  id: string;
  fecha: string;
  tipo: TipoNotificacion;
  icono: string;
  traderNombre?: string;
  traderAddress?: string;
  coin?: string;
  lado?: 'Long' | 'Short' | null;
  accion?: string;
  montoUsd?: number | null;
  precio?: number | null;
  nTraders?: number;
  texto?: string;
}

// verbo de un movimiento (ver candidatos.service.ts) -> accion en pasado
// para el texto de la notificacion
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

const MAX_DIAS = 30;

// Notificaciones -- basado en los disparadores reales que tenia la app
// vieja (crear_notificacion en refresher.py/descubrimiento.py), menos el
// resumen semanal de descubrimiento completo (decision explicita: no
// interesa salvo que aparezca alguien "subrumal top", eso se aparca para
// mas adelante). Todo filtrado por usuario via CandidatosService (que ya
// filtra consenso/posiciones por SeguidosService); los traders desestimados
// se leen directamente del pool de candidatos.
@Injectable({ providedIn: 'root' })
export class NotificacionesService {
  private readonly candidatos = inject(CandidatosService);
  private readonly seguidos = inject(SeguidosService);
  private readonly leidas = signal<ReadonlySet<string>>(new Set());

  readonly items = computed<NotificacionItem[]>(() => {
    const corte = new Date(Date.now() - MAX_DIAS * 24 * 60 * 60 * 1000).toISOString();

    const deConsenso: NotificacionItem[] = this.candidatos
      .consensoSeguido()
      .map((g) => ({
        id: `consenso_${g.coin}_${g.lado}`,
        fecha: g.traders.map((t) => t.fecha).sort().at(-1)!,
        tipo: 'consenso' as const,
        icono: 'pi-bolt',
        coin: g.coin,
        lado: g.lado,
        nTraders: g.traders.length,
        accion: g.verbo,
      }))
      .filter((n) => n.fecha >= corte);

    // no tiene sentido notificar un movimiento de ANTES de empezar a seguir
    // a ese trader -- ni uno de hace mas de MAX_DIAS, aunque siga siendolo
    const deTrading: NotificacionItem[] = this.candidatos.posicionesTrading().flatMap((p) =>
      (p.movimientos ?? [])
        .filter((m) => m.fecha >= corte && m.fecha >= (this.seguidos.desde(p.traderAddress) ?? corte))
        .map((m, i) => ({
          id: `trading_${p.traderAddress}_${p.coin}_${i}`,
          fecha: m.fecha,
          tipo: 'trading' as const,
          icono: 'pi-chart-line',
          traderNombre: p.traderNombre,
          traderAddress: p.traderAddress,
          coin: m.coin ?? p.coin,
          lado: m.lado ?? p.lado,
          accion: ACCION_TRADING[m.verbo] ?? m.verbo,
          montoUsd: m.notionalUsd,
          precio: m.precio,
        })),
    );

    const deSpot: NotificacionItem[] = this.candidatos.posicionesSpot().flatMap((p) =>
      (p.movimientos ?? [])
        .filter((m) => m.fecha >= corte && m.fecha >= (this.seguidos.desde(p.traderAddress) ?? corte))
        .map((m, i) => ({
          id: `spot_${p.traderAddress}_${p.coin}_${i}`,
          fecha: m.fecha,
          tipo: 'spot' as const,
          icono: 'pi-wallet',
          traderNombre: p.traderNombre,
          traderAddress: p.traderAddress,
          coin: m.coin ?? p.coin,
          lado: null,
          accion: ACCION_SPOT[m.verbo] ?? m.verbo,
          montoUsd: m.notionalUsd,
          precio: m.precio,
        })),
    );

    const deDesestimados: NotificacionItem[] = this.candidatos
      .candidatos()
      .filter((c) => c.desestimado && this.seguidos.estaSiguiendo(c.address))
      .map((c) => ({
        id: `desestimado_${c.address}`,
        fecha: c.desestimado!.fecha,
        tipo: 'desestimado' as const,
        icono: 'pi-user-minus',
        traderNombre: c.nombre,
        traderAddress: c.address,
        texto: `ha sido desestimado del descubrimiento (${c.desestimado!.motivo}) -- has perdido esa posición`,
      }))
      .filter((n) => n.fecha >= corte);

    return [...deConsenso, ...deTrading, ...deSpot, ...deDesestimados].sort((a, b) => b.fecha.localeCompare(a.fecha));
  });

  readonly hayNoLeidas = computed(() => this.items().some((n) => !this.leidas().has(n.id)));

  marcarTodasLeidas(): void {
    this.leidas.set(new Set(this.items().map((n) => n.id)));
  }
}
