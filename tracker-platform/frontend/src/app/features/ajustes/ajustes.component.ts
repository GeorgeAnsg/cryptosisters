import { Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ToggleSwitch } from 'primeng/toggleswitch';
import { Button } from 'primeng/button';
import { Tabs, TabList, Tab, TabPanels, TabPanel } from 'primeng/tabs';
import { CribadoComponent } from '../traders/cribado/cribado.component';
import { CandidatosService } from '../../core/candidatos/candidatos.service';
import { AjustesService } from '../../core/ajustes/ajustes.service';
import { etiquetaMoneda } from '../../shared/utils/moneda';

// pestaña Ajustes -- dos tabs: Monedas (whitelist aplicada a TODA la
// plataforma via AjustesService/CandidatosService, no solo al push) y
// Cribado (los parametros de descubrimiento, movido aqui desde el submenu
// de Traders por no ser una vista de traders en si).
@Component({
  selector: 'app-ajustes',
  standalone: true,
  imports: [FormsModule, ToggleSwitch, Button, Tabs, TabList, Tab, TabPanels, TabPanel, CribadoComponent],
  templateUrl: './ajustes.component.html',
})
export class AjustesComponent {
  private readonly candidatos = inject(CandidatosService);
  protected readonly ajustes = inject(AjustesService);

  // orden de prioridad para agrupar la rejilla -- cripto primero (lo que
  // de verdad se sigue dia a dia), luego indices/materias primas (SP500,
  // oro...), acciones y divisas al final
  private static readonly ORDEN_CATEGORIA: Record<string, number> = {
    Cripto: 0, Índice: 1, 'Materia prima': 2, Acción: 3, Divisa: 4,
  };

  // monedas unicas (con alias BTC/UBTC etc. ya fundidos -- sin esto salian
  // como dos opciones distintas, siendo la misma moneda) de todos los
  // candidatos, no solo los seguidos -- cualquiera puede llegar a seguir.
  // Ordenadas por categoria y, dentro de cada una, alfabeticamente.
  protected readonly monedasDisponibles = computed(() => {
    const categoriaDe = new Map<string, string>();
    for (const c of this.candidatos.candidatos()) {
      for (const m of c.monedas) {
        const nombre = etiquetaMoneda(m.nombre);
        if (!categoriaDe.has(nombre)) categoriaDe.set(nombre, m.categoria);
      }
    }
    return [...categoriaDe.keys()].sort((a, b) => {
      const pa = AjustesComponent.ORDEN_CATEGORIA[categoriaDe.get(a)!] ?? 99;
      const pb = AjustesComponent.ORDEN_CATEGORIA[categoriaDe.get(b)!] ?? 99;
      return pa !== pb ? pa - pb : a.localeCompare(b);
    });
  });

  // borrador local -- se guarda explicitamente (boton), no en cada toggle,
  // para no disparar un PUT por cada moneda que marcas/desmarcas
  protected readonly seleccion = signal<string[]>([]);
  protected readonly guardando = signal(false);

  // sincroniza el borrador con lo cargado del backend -- al entrar en la
  // pagina (llega con retraso, la carga es async) y si cambia de usuario
  constructor() {
    effect(() => this.seleccion.set([...this.ajustes.monedasNotificar()]));
  }

  protected activa(moneda: string): boolean {
    return this.seleccion().includes(moneda);
  }

  protected alternar(moneda: string, activa: boolean): void {
    this.seleccion.update((lista) => (activa ? [...lista, moneda] : lista.filter((m) => m !== moneda)));
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
