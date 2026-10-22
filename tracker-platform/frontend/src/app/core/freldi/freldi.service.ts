import { Injectable, effect, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from '../auth/auth.service';

export interface FreldiScoreItem {
  score10: number;
  label: string;
  rationale: string;
}

export interface FreldiScores {
  F: FreldiScoreItem;
  R: FreldiScoreItem;
  E: FreldiScoreItem;
  D: FreldiScoreItem;
  L: FreldiScoreItem;
  I: FreldiScoreItem;
  X: FreldiScoreItem;
  total100: number;
  buySignal: string;
  confidence: string;
}

export interface FreldiSourceHealth {
  status: 'ok' | 'cached' | 'stale' | 'blocked';
  ageHours?: number | null;
  message?: string | null;
}

export interface FreldiSnapshot {
  fearAndGreed?: { value: number; zone: string; trend: string };
  rsi?: { daily?: { value: number }; weekly?: { value: number } };
  dxy?: { value: number };
  liquidity?: { value: number };
  vix?: { value: number };
  googleInterest?: number;
  scores?: FreldiScores;
  status?: 'ok' | 'degraded';
  sourcesHealth?: Record<string, FreldiSourceHealth>;
}

// snapshot del indice FRELDI(X) -- lo calcula otra app del usuario
// (Multivac), aqui solo se pide lo ya cacheado (ver backend/freldi.py: se
// recalcula como mucho una vez al dia, nunca en caliente desde el frontend)
@Injectable({ providedIn: 'root' })
export class FreldiService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  private readonly snapshot = signal<FreldiSnapshot | null>(null);
  private readonly actualizadoTs = signal<number | null>(null);
  private readonly cargando = signal(false);
  private readonly error = signal(false);

  readonly datos = this.snapshot.asReadonly();
  readonly actualizado = this.actualizadoTs.asReadonly();
  readonly estaCargando = this.cargando.asReadonly();
  readonly huboError = this.error.asReadonly();

  // igual que AjustesService/CandidatosService: reacciona a auth.uid(), no
  // se llama desde el componente al construirse -- llamarlo una sola vez
  // desde FreldiComponent corria la carrera con el token de Firebase aun no
  // listo (401) si se entraba a /freldi en una carga fria de la app
  constructor() {
    effect(() => {
      if (this.auth.uid()) this.refrescar();
    });
  }

  async refrescar(): Promise<void> {
    if (!this.auth.uid()) return;
    this.cargando.set(true);
    this.error.set(false);
    try {
      const res = await firstValueFrom(
        this.http.get<{ data: FreldiSnapshot | null; actualizadoTs: number | null }>(`${environment.apiUrl}/freldi`),
      );
      this.snapshot.set(res.data);
      this.actualizadoTs.set(res.actualizadoTs);
    } catch {
      this.error.set(true);
    } finally {
      this.cargando.set(false);
    }
  }
}
