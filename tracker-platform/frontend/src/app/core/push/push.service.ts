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

  // los tres botones (activar/desactivar/probar) son el unico sitio donde
  // esto puede fallar visiblemente para el usuario -- sin esto, un error
  // (permiso denegado, VAPID mal puesto en el backend, red...) quedaba como
  // promesa rechazada sin manejar, es decir: "no hace nada" en apariencia
  async activar(): Promise<void> {
    try {
      if (!this.disponible) {
        alert('Este navegador/dispositivo no soporta notificaciones push (o no estás en HTTPS).');
        return;
      }
      // en iPhone/iPad, PushManager NO existe en una pestaña normal de
      // Safari -- solo cuando la app esta instalada en pantalla de inicio
      // Y abierta desde ahi. Sin este chequeo, el error que da iOS es un
      // "undefined is not an object" ilegible en vez de esto
      if (!('PushManager' in window)) {
        alert('En iPhone/iPad, las notificaciones solo funcionan si añades la app a la pantalla de inicio (botón compartir → "Añadir a pantalla de inicio") y la abres desde ese icono, no desde Safari.');
        return;
      }
      const { clave } = await firstValueFrom(this.http.get<{ clave: string | null }>(`${environment.apiUrl}/push/clave-publica`));
      if (!clave) {
        alert('El backend no tiene configuradas las claves VAPID (VAPID_PUBLIC_KEY) -- revísalo en Coolify.');
        return;
      }
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
    } catch (e) {
      console.error('push.activar', e);
      alert('No se pudo activar: ' + this.describirError(e));
    }
  }

  async desactivar(): Promise<void> {
    try {
      const sub = await firstValueFrom(this.swPush.subscription);
      if (!sub) return;
      const endpoint = sub.endpoint;
      await sub.unsubscribe();
      await firstValueFrom(this.http.delete(`${environment.apiUrl}/push/suscribirse`, { params: { endpoint } }));
      this.suscrito.set(false);
    } catch (e) {
      console.error('push.desactivar', e);
      alert('No se pudo desactivar: ' + this.describirError(e));
    }
  }

  async probar(): Promise<void> {
    try {
      const r = await firstValueFrom(
        this.http.post<{ configurado: boolean; enviados: number; fallidos: number; suscripciones: number }>(
          `${environment.apiUrl}/push/probar`,
          {},
        ),
      );
      if (!r.configurado) {
        alert('El backend no tiene las claves VAPID puestas (VAPID_PRIVATE_KEY/VAPID_PUBLIC_KEY) -- revísalo en Coolify.');
      } else if (r.suscripciones === 0) {
        alert('No hay ninguna suscripción guardada en el backend -- prueba a desactivar y volver a activar los avisos.');
      } else if (r.enviados === 0) {
        alert(`Se intentó enviar a ${r.suscripciones} suscripción(es) pero todas fallaron (${r.fallidos}). Mira los logs del backend.`);
      } else {
        alert(`Prueba enviada a ${r.enviados}/${r.suscripciones} dispositivo(s). Debería saltarte en unos segundos.`);
      }
    } catch (e) {
      console.error('push.probar', e);
      alert('No se pudo enviar la prueba: ' + this.describirError(e));
    }
  }

  private describirError(e: unknown): string {
    if (e && typeof e === 'object' && 'message' in e) return String((e as { message: unknown }).message);
    return String(e);
  }
}
