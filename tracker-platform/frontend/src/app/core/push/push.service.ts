import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { SwPush } from '@angular/service-worker';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';

// activar/desactivar las notificaciones push del navegador -- el broadcast
// en si (Abre/Añade/Cierra, consenso) lo manda el backend (ver
// app/services/push.py), esto solo gestiona la suscripcion de ESTE
// dispositivo contra ese broadcast
@Injectable({ providedIn: 'root' })
export class PushService {
  private readonly swPush = inject(SwPush);
  private readonly http = inject(HttpClient);

  readonly suscrito = signal(false);
  readonly disponible = this.swPush.isEnabled;

  constructor() {
    if (this.disponible) {
      this.swPush.subscription.subscribe((s) => this.suscrito.set(!!s));
    }
  }

  async activar(): Promise<void> {
    if (!this.disponible) return;
    const { clave } = await firstValueFrom(this.http.get<{ clave: string | null }>(`${environment.apiUrl}/push/clave-publica`));
    if (!clave) return;
    const sub = await this.swPush.requestSubscription({ serverPublicKey: clave });
    const json = sub.toJSON();
    await firstValueFrom(
      this.http.post(`${environment.apiUrl}/push/suscribirse`, {
        endpoint: json.endpoint,
        p256dh: json.keys!['p256dh'],
        auth: json.keys!['auth'],
      }),
    );
    this.suscrito.set(true);
  }

  async desactivar(): Promise<void> {
    const sub = await firstValueFrom(this.swPush.subscription);
    if (!sub) return;
    const endpoint = sub.endpoint;
    await sub.unsubscribe();
    await firstValueFrom(this.http.delete(`${environment.apiUrl}/push/suscribirse`, { params: { endpoint } }));
    this.suscrito.set(false);
  }

  async probar(): Promise<void> {
    await firstValueFrom(this.http.post(`${environment.apiUrl}/push/probar`, {}));
  }
}
