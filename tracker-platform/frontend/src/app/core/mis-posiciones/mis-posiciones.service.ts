import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from '../auth/auth.service';

export interface MiPosicion {
  clave: string;
  traderAddress: string;
  tipo: 'trading' | 'spot';
  coin: string;
  lado: 'Long' | 'Short' | null;
  estado: 'abierta' | 'cerrada';
  fechaApertura: number;
  fechaCierre: number | null;
  pnl: number | null;
}

// posiciones que el usuario ha "abierto" el mismo copiando a un trader que
// sigue -- boton Abrir en Posiciones. Nunca se borra solo (equivalente a
// mis_posiciones en la app vieja): se cierra a mano con tu propio resultado,
// eso es lo que luego alimenta Estadisticas.
@Injectable({ providedIn: 'root' })
export class MisPosicionesService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  private readonly lista = signal<readonly MiPosicion[]>([]);

  constructor() {
    effect(() => {
      const uid = this.auth.uid();
      if (uid) {
        firstValueFrom(this.http.get<MiPosicion[]>(`${environment.apiUrl}/mis-posiciones`))
          .then((l) => this.lista.set(l))
          .catch(() => this.lista.set([]));
      } else {
        this.lista.set([]);
      }
    });
  }

  readonly abiertas = computed(() => this.lista().filter((m) => m.estado === 'abierta'));
  readonly cerradas = computed(() => this.lista().filter((m) => m.estado === 'cerrada'));

  estaAbierta(clave: string): boolean {
    return this.abiertas().some((m) => m.clave === clave);
  }

  async abrir(clave: string, traderAddress: string, tipo: 'trading' | 'spot', coin: string, lado: string | null): Promise<void> {
    await firstValueFrom(this.http.put(`${environment.apiUrl}/mis-posiciones/${clave}`, { traderAddress, tipo, coin, lado }));
    this.lista.update((actual) => [
      ...actual,
      { clave, traderAddress, tipo, coin, lado: lado as MiPosicion['lado'], estado: 'abierta', fechaApertura: Date.now(), fechaCierre: null, pnl: null },
    ]);
  }

  async cerrar(clave: string, pnl: number): Promise<void> {
    await firstValueFrom(this.http.put(`${environment.apiUrl}/mis-posiciones/${clave}/cerrar`, { pnl }));
    this.lista.update((actual) =>
      actual.map((m) => (m.clave === clave ? { ...m, estado: 'cerrada', fechaCierre: Date.now(), pnl } : m)),
    );
  }
}
