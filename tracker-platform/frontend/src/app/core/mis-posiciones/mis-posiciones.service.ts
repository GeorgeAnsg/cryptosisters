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
  // precio del activo en el instante en que el usuario abrio esta copia
  // (capturado por el backend, no el entryPx del trader) -- null en
  // posiciones abiertas antes de este campo, o si Hyperliquid no respondio
  precioEntrada: number | null;
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
      if (this.auth.uid()) this.refrescar();
      else this.lista.set([]);
    });
  }

  // se pide al iniciar sesion y de nuevo cada vez que se entra a la pantalla
  // (ver MisPosicionesComponent) -- nunca en segundo plano
  refrescar(): void {
    firstValueFrom(this.http.get<MiPosicion[]>(`${environment.apiUrl}/mis-posiciones`))
      .then((l) => this.lista.set(l))
      .catch(() => {});
  }

  readonly abiertas = computed(() => this.lista().filter((m) => m.estado === 'abierta'));
  readonly cerradas = computed(() => this.lista().filter((m) => m.estado === 'cerrada'));

  estaAbierta(clave: string): boolean {
    return this.abiertas().some((m) => m.clave === clave);
  }

  // % en vivo de una posicion ABIERTA, a TU propio precio de entrada
  // (precioEntrada, capturado al abrir) comparado con el precio actual real
  // del activo -- ya no se copia el % del trader asumiendo que entraste a
  // su mismo precio. Si no hay precioEntrada (posiciones abiertas antes de
  // este campo, o fallo al capturarlo), cae al viejo comportamiento
  // aproximado para no dejarlas sin ningun dato.
  pctEnVivo(m: MiPosicion): number | null {
    const p =
      m.tipo === 'trading'
        ? this.candidatos.posicionesTrading().find((x) => x.traderAddress === m.traderAddress && x.coin === m.coin && x.lado === m.lado)
        : this.candidatos.posicionesSpot().find((x) => x.traderAddress === m.traderAddress && x.coin === m.coin);
    if (!p) return null;
    if (m.precioEntrada) {
      const signo = m.tipo === 'trading' && m.lado === 'Short' ? -1 : 1;
      return ((p.precioActual - m.precioEntrada) / m.precioEntrada) * 100 * signo;
    }
    if (p.resultadoUsd == null || !p.invertidoUsd) return null;
    return (p.resultadoUsd / p.invertidoUsd) * 100;
  }

  usdEnVivo(m: MiPosicion): number | null {
    const pct = this.pctEnVivo(m);
    return pct == null || m.montoInvertido == null ? null : (m.montoInvertido * pct) / 100;
  }

  // true si el trader copiado ya no tiene esta posicion abierta -- avisa
  // para que el usuario cierre tambien la suya. Antes de que lleguen datos
  // de candidatos (candidatos().length === 0) no se puede distinguir "la
  // cerro" de "aun no hemos cargado nada", así que no se avisa en falso.
  traderCerro(m: MiPosicion): boolean {
    if (m.estado !== 'abierta' || !this.candidatos.candidatos().length) return false;
    const sigueAbierta =
      m.tipo === 'trading'
        ? this.candidatos.posicionesTrading().some((x) => x.traderAddress === m.traderAddress && x.coin === m.coin && x.lado === m.lado)
        : this.candidatos.posicionesSpot().some((x) => x.traderAddress === m.traderAddress && x.coin === m.coin);
    return !sigueAbierta;
  }

  async abrir(
    clave: string,
    traderAddress: string,
    tipo: 'trading' | 'spot',
    coin: string,
    lado: string | null,
    montoInvertido: number | null,
  ): Promise<void> {
    const res = await firstValueFrom(
      this.http.put<{ ok: boolean; precioEntrada: number | null }>(`${environment.apiUrl}/mis-posiciones/${clave}`, {
        traderAddress, tipo, coin, lado, montoInvertido,
      }),
    );
    this.lista.update((actual) => [
      ...actual,
      {
        clave, traderAddress, tipo, coin, lado: lado as MiPosicion['lado'],
        estado: 'abierta', fechaApertura: Date.now(), fechaCierre: null, pnl: null, montoInvertido,
        precioEntrada: res.precioEntrada,
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
