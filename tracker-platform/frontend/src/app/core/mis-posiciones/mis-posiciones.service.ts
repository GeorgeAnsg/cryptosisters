import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from '../auth/auth.service';
import { CandidatosService } from '../candidatos/candidatos.service';

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
  montoInvertido: number | null;
}

// posiciones que el usuario ha "abierto" el mismo copiando a un trader que
// sigue -- boton Abrir en Posiciones. Nunca se borra solo (equivalente a
// mis_posiciones en la app vieja): se cierra a mano con tu propio resultado,
// eso es lo que luego alimenta Estadisticas.
@Injectable({ providedIn: 'root' })
export class MisPosicionesService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly candidatos = inject(CandidatosService);

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

  // % en vivo de una posicion ABIERTA -- el del trader copiado, aplicado a
  // lo que tu invertiste (asume misma entrada que el; es una estimacion,
  // no un seguimiento propio de precio). Null si el trader ya no tiene esa
  // posicion o no sabemos cuanto invertiste. Usado tanto en el resumen del
  // Dashboard como en la tabla completa de Mis Posiciones.
  pctEnVivo(m: MiPosicion): number | null {
    const p =
      m.tipo === 'trading'
        ? this.candidatos.posicionesTrading().find((x) => x.traderAddress === m.traderAddress && x.coin === m.coin && x.lado === m.lado)
        : this.candidatos.posicionesSpot().find((x) => x.traderAddress === m.traderAddress && x.coin === m.coin);
    if (!p || p.resultadoUsd == null || !p.invertidoUsd) return null;
    return (p.resultadoUsd / p.invertidoUsd) * 100;
  }

  usdEnVivo(m: MiPosicion): number | null {
    const pct = this.pctEnVivo(m);
    return pct == null || m.montoInvertido == null ? null : (m.montoInvertido * pct) / 100;
  }

  async abrir(
    clave: string,
    traderAddress: string,
    tipo: 'trading' | 'spot',
    coin: string,
    lado: string | null,
    montoInvertido: number | null,
  ): Promise<void> {
    await firstValueFrom(this.http.put(`${environment.apiUrl}/mis-posiciones/${clave}`, { traderAddress, tipo, coin, lado, montoInvertido }));
    this.lista.update((actual) => [
      ...actual,
      {
        clave, traderAddress, tipo, coin, lado: lado as MiPosicion['lado'],
        estado: 'abierta', fechaApertura: Date.now(), fechaCierre: null, pnl: null, montoInvertido,
      },
    ]);
  }

  // delta positivo = añade, negativo = reduce (ver btn-abrir/op-flecha de
  // la app vieja: aqui el usuario dice cuanto mueve, no se infiere)
  async ajustar(clave: string, delta: number): Promise<void> {
    await firstValueFrom(this.http.put(`${environment.apiUrl}/mis-posiciones/${clave}/ajustar`, { delta }));
    this.lista.update((actual) =>
      actual.map((m) => (m.clave === clave ? { ...m, montoInvertido: Math.max(0, (m.montoInvertido ?? 0) + delta) } : m)),
    );
  }

  async cerrar(clave: string, pnl: number): Promise<void> {
    await firstValueFrom(this.http.put(`${environment.apiUrl}/mis-posiciones/${clave}/cerrar`, { pnl }));
    this.lista.update((actual) =>
      actual.map((m) => (m.clave === clave ? { ...m, estado: 'cerrada', fechaCierre: Date.now(), pnl } : m)),
    );
  }
}
