import { Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MultiSelect } from 'primeng/multiselect';
import { Button } from 'primeng/button';
import { Tabs, TabList, Tab, TabPanels, TabPanel } from 'primeng/tabs';
import { CribadoComponent } from '../traders/cribado/cribado.component';
import { CandidatosService } from '../../core/candidatos/candidatos.service';
import { AjustesService } from '../../core/ajustes/ajustes.service';

// pestaña Ajustes -- de momento dos tabs: Notificaciones (whitelist de
// monedas, aplicada a TODA la plataforma via AjustesService/CandidatosService,
// no solo al push) y Cribado (los parametros de descubrimiento, movido aqui
// desde el submenu de Traders por no ser una vista de traders en si).
@Component({
  selector: 'app-ajustes',
  standalone: true,
  imports: [FormsModule, MultiSelect, Button, Tabs, TabList, Tab, TabPanels, TabPanel, CribadoComponent],
  templateUrl: './ajustes.component.html',
})
export class AjustesComponent {
  private readonly candidatos = inject(CandidatosService);
  protected readonly ajustes = inject(AjustesService);

  protected readonly opcionesMonedas = computed(() =>
    [...new Set(this.candidatos.candidatos().flatMap((c) => c.monedas.map((m) => m.nombre)))].sort().map((nombre) => ({ label: nombre, value: nombre })),
  );

  // borrador local -- se guarda explicitamente (boton), no en cada click
  // del multiselect, para no disparar un PUT por cada moneda que marcas
  protected readonly seleccion = signal<string[]>([]);
  protected readonly guardando = signal(false);

  // sincroniza el borrador con lo cargado del backend -- al entrar en la
  // pagina (llega con retraso, la carga es async) y si cambia de usuario
  constructor() {
    effect(() => this.seleccion.set([...this.ajustes.monedasNotificar()]));
  }

  protected async guardar(): Promise<void> {
    this.guardando.set(true);
    try {
      await this.ajustes.guardar(this.seleccion());
    } finally {
      this.guardando.set(false);
    }
  }
}
