import { Injectable, computed, signal } from '@angular/core';

// contador en vez de un simple boolean -- si hay varias peticiones a la vez
// (ej. dos widgets del dashboard cargando en paralelo), el loader no debe
// desaparecer hasta que termine la ULTIMA, no la primera.
@Injectable({ providedIn: 'root' })
export class LoadingService {
  private readonly peticionesActivas = signal(0);
  readonly cargando = computed(() => this.peticionesActivas() > 0);

  empezar(): void {
    this.peticionesActivas.update((n) => n + 1);
  }

  terminar(): void {
    this.peticionesActivas.update((n) => Math.max(0, n - 1));
  }
}
