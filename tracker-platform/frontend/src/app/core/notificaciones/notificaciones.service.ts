import { Injectable, computed, inject, signal } from '@angular/core';
import { CandidatosService } from '../candidatos/candidatos.service';
import { SeguidosService } from '../seguidos/seguidos.service';

export interface NotificacionItem {
  id: string;
  fecha: string;
  icono: string;
  texto: string;
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
    const deConsenso: NotificacionItem[] = this.candidatos
      .consensoSeguido()
      .map((g) => ({
        id: `consenso_${g.coin}_${g.lado}`,
        fecha: g.traders.map((t) => t.fecha).sort().at(-1)!,
        icono: 'pi-bolt',
        texto: `Consenso: ${g.traders.length} traders ${g.lado} ${g.verbo} en ${g.coin}`,
      }));

    const deTrading: NotificacionItem[] = this.candidatos.posicionesTrading().flatMap((p) =>
      (p.movimientos ?? []).map((m, i) => ({
        id: `trading_${p.traderAddress}_${p.coin}_${i}`,
        fecha: m.fecha,
        icono: 'pi-chart-line',
        texto: `${p.traderNombre} ${ACCION_TRADING[m.verbo] ?? m.verbo} ${p.lado} en ${p.coin}`,
      })),
    );

    const deSpot: NotificacionItem[] = this.candidatos.posicionesSpot().flatMap((p) =>
      (p.movimientos ?? []).map((m, i) => ({
        id: `spot_${p.traderAddress}_${p.coin}_${i}`,
        fecha: m.fecha,
        icono: 'pi-wallet',
        texto: `${p.traderNombre} ${ACCION_SPOT[m.verbo] ?? m.verbo} ${p.coin} en spot`,
      })),
    );

    const deDesestimados: NotificacionItem[] = this.candidatos
      .candidatos()
      .filter((c) => c.desestimado && this.seguidos.estaSiguiendo(c.address))
      .map((c) => ({
        id: `desestimado_${c.address}`,
        fecha: c.desestimado!.fecha,
        icono: 'pi-user-minus',
        texto: `${c.nombre} ha sido desestimado del descubrimiento (${c.desestimado!.motivo}) -- has perdido esa posición`,
      }));

    return [...deConsenso, ...deTrading, ...deSpot, ...deDesestimados].sort((a, b) => b.fecha.localeCompare(a.fecha));
  });

  readonly hayNoLeidas = computed(() => this.items().some((n) => !this.leidas().has(n.id)));

  marcarTodasLeidas(): void {
    this.leidas.set(new Set(this.items().map((n) => n.id)));
  }
}
