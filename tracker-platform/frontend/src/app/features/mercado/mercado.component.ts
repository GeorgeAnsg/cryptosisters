import { Component, computed, inject } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FilaMercadoSpot, FilaMercadoTrading } from './mercado.model';
import { CandidatosService } from '../../core/candidatos/candidatos.service';

// monedas "de referencia" siempre arriba del todo, igual que
// PRIORIDAD_MERCADO en la app vieja -- antes de ordenar el resto por $
// expuesto, para tener de un vistazo las que realmente importan
const PRIORIDAD_MERCADO = ['BTC', 'HYPE', 'ETH', 'BNB'];
// una moneda con menos traders no es señal de mercado, es una apuesta
// individual -- se necesitan varios de acuerdo para que signifique algo
const MINIMO_TRADERS = 5;

function ordenarPorPrioridad<T>(filas: T[], coinDe: (f: T) => string, valorDe: (f: T) => number): T[] {
  return [...filas].sort((a, b) => {
    const pa = PRIORIDAD_MERCADO.indexOf(coinDe(a));
    const pb = PRIORIDAD_MERCADO.indexOf(coinDe(b));
    if (pa !== -1 || pb !== -1) return (pa === -1 ? 999 : pa) - (pb === -1 ? 999 : pb);
    return valorDe(b) - valorDe(a);
  });
}

// percepcion de mercado agregada sobre TODOS los candidatos descubiertos
// (no solo a quien sigues) -- largos vs cortos en trading, y lo mas
// sostenido en spot. Misma logica que renderPaginaMercado() en la app
// vieja (backend/static/index.html), con datos de mentira por ahora.
@Component({
  selector: 'app-mercado',
  standalone: true,
  imports: [DecimalPipe],
  templateUrl: './mercado.component.html',
})
export class MercadoComponent {
  private readonly candidatos = inject(CandidatosService);
  private readonly trading = this.candidatos.mercadoTrading;
  private readonly spot = this.candidatos.mercadoSpot;

  protected readonly filasTrading = computed(() =>
    ordenarPorPrioridad(
      this.trading().filter((f) => f.nLong + f.nShort >= MINIMO_TRADERS),
      (f) => f.coin,
      (f) => f.dLong + f.dShort,
    ),
  );

  protected readonly filasSpot = computed(() =>
    ordenarPorPrioridad(
      this.spot().filter((f) => f.n >= MINIMO_TRADERS),
      (f) => f.coin,
      (f) => f.d,
    ),
  );

  protected readonly maxSpotN = computed(() => Math.max(1, ...this.filasSpot().map((f) => f.n)));

  protected pctLong(f: FilaMercadoTrading): number {
    const total = f.nLong + f.nShort;
    return total ? (f.nLong / total) * 100 : 50;
  }

  protected anchoSpot(f: FilaMercadoSpot): number {
    return Math.max(6, (f.n / this.maxSpotN()) * 100);
  }
}
