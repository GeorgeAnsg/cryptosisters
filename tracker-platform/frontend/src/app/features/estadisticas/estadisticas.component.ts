import { Component } from '@angular/core';

// equivalente a renderPaginaStats() en la app vieja: TU resultado (lo que
// tu mismo has abierto desde "Posiciones abiertas" y cerrado despues), no
// el de los traders que sigues. Depende del sistema de copy-trading propio
// (misPosiciones) que este rebuild todavia no tiene montado, asi que de
// momento siempre esta en su estado vacio -- igual que el "Mis posiciones"
// del Dashboard.
@Component({
  selector: 'app-estadisticas',
  standalone: true,
  template: `
    <div class="mb-3.5 font-display text-lg font-semibold">Estadísticas</div>
    <div class="panel flex flex-col items-center gap-2 p-panel py-16 text-center">
      <i class="pi pi-chart-bar text-2xl text-fg-muted"></i>
      <span class="text-base text-fg-muted">
        Todavía no has cerrado ninguna posición propia — esto se rellena cuando abras algo desde "Posiciones abiertas" y luego lo cierres.
      </span>
    </div>
  `,
})
export class EstadisticasComponent {}
