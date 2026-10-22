import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from '../auth/auth.service';
import { etiquetaMoneda } from '../../shared/utils/moneda';

// whitelist de monedas del usuario -- vacia = sin restriccion (todas). Se
// aplica en TODA la plataforma a lo que es "tuyo" (Dashboard, Posiciones,
// Consenso, Notificaciones, push), igual que SeguidosService: la rejilla
// de descubrimiento de Traders y Mercado NO se filtran por esto, son el
// pool global del que se elige a quien seguir/que te interesa.
@Injectable({ providedIn: 'root' })
export class AjustesService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  private readonly monedas = signal<readonly string[]>([]);

  constructor() {
    effect(() => {
      const uid = this.auth.uid();
      if (uid) {
        firstValueFrom(this.http.get<{ monedasNotificar: string[] }>(`${environment.apiUrl}/ajustes`))
          .then((a) => this.monedas.set(a.monedasNotificar))
          .catch(() => this.monedas.set([]));
      } else {
        this.monedas.set([]);
      }
    });
  }

  readonly monedasNotificar = computed(() => this.monedas());

  // vacia = no filtra nada (todas las monedas pasan)
  pasaFiltro(coin: string): boolean {
    const lista = this.monedas();
    return lista.length === 0 || lista.includes(etiquetaMoneda(coin));
  }

  async guardar(monedas: string[]): Promise<void> {
    const anterior = this.monedas();
    this.monedas.set(monedas);
    try {
      await firstValueFrom(this.http.put(`${environment.apiUrl}/ajustes`, { monedasNotificar: monedas }));
    } catch {
      this.monedas.set(anterior);
    }
  }
}
