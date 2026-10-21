import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from '../auth/auth.service';

// lista de traders que sigue el usuario logueado -- un solo sitio del que
// cuelga todo lo que debe filtrarse "por usuario" (Posiciones, Dashboard,
// Consenso); Traders > Trading/Spot (la rejilla de descubrimiento) y
// Mercado NO se filtran por esto, son el pool global del que se elige a
// quien seguir.
@Injectable({ providedIn: 'root' })
export class SeguidosService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  // direccion -> fecha ISO desde la que la sigue (para filtrar, ver
  // Notificaciones: no tiene sentido notificar de un movimiento de ANTES de
  // empezar a seguir a ese trader)
  private readonly seguidos = signal<ReadonlyMap<string, string>>(new Map());

  constructor() {
    // recarga la lista cada vez que cambia quien esta logueado (incluido al
    // cerrar sesion, que la vacia) -- asi un usuario nuevo nunca hereda lo
    // que veia el anterior
    effect(() => {
      const uid = this.auth.uid();
      if (uid) {
        firstValueFrom(this.http.get<{ address: string; desde: string }[]>(`${environment.apiUrl}/usuarios/sigue`))
          .then((filas) => this.seguidos.set(new Map(filas.map((f) => [f.address, `${f.desde.replace(' ', 'T')}Z`]))))
          .catch(() => this.seguidos.set(new Map()));
      } else {
        this.seguidos.set(new Map());
      }
    });
  }

  estaSiguiendo(traderAddress: string): boolean {
    return this.seguidos().has(traderAddress);
  }

  desde(traderAddress: string): string | null {
    return this.seguidos().get(traderAddress) ?? null;
  }

  // computed, no metodo -- para usarlo directamente en una plantilla o un
  // computed() de otro componente sin volver a pedir la lista
  readonly direcciones = computed(() => new Set(this.seguidos().keys()));

  async establecer(traderAddress: string, siguiendo: boolean): Promise<void> {
    // optimista: refleja el cambio al instante, revierte si el backend falla
    const anterior = this.seguidos();
    const siguiente = new Map(anterior);
    siguiendo ? siguiente.set(traderAddress, new Date().toISOString()) : siguiente.delete(traderAddress);
    this.seguidos.set(siguiente);

    try {
      if (siguiendo) {
        await firstValueFrom(this.http.put(`${environment.apiUrl}/usuarios/sigue/${traderAddress}`, {}));
      } else {
        await firstValueFrom(this.http.delete(`${environment.apiUrl}/usuarios/sigue/${traderAddress}`));
      }
    } catch {
      this.seguidos.set(anterior);
    }
  }
}
