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

  // dentro de cada categoria, los activos "de referencia" van antes que el
  // resto (que queda en orden alfabetico) -- sin esto Bitcoin se perdia
  // alfabeticamente entre el resto de criptos
  private static readonly PRIORIDAD_ACTIVO: Record<string, number> = {
    BTC: 0, ETH: 1, SOL: 2, HYPE: 3,
    SP500: 0, US500: 0, USA500: 0,
    GOLD: 0, SILVER: 1,
  };

  // activos unicos (con alias BTC/UBTC etc. ya fundidos -- sin esto salian
  // como dos opciones distintas, siendo el mismo activo) de todos los
  // candidatos, no solo los seguidos -- cualquiera puede llegar a seguir.
  // Agrupados por categoria (en el orden de arriba) y, dentro de cada una,
  // por prioridad y despues alfabeticamente.
  protected readonly grupos = computed(() => {
    const categoriaDe = new Map<string, string>();
    for (const c of this.candidatos.candidatos()) {
      for (const m of c.monedas) {
        const nombre = etiquetaMoneda(m.nombre);
        if (!categoriaDe.has(nombre)) categoriaDe.set(nombre, m.categoria);
      }
    }
    const porCategoria = new Map<string, string[]>();
    for (const [nombre, categoria] of categoriaDe) {
      (porCategoria.get(categoria) ?? porCategoria.set(categoria, []).get(categoria)!).push(nombre);
    }
    return [...porCategoria.entries()]
      .sort(([a], [b]) => (AjustesComponent.ORDEN_CATEGORIA[a] ?? 99) - (AjustesComponent.ORDEN_CATEGORIA[b] ?? 99))
      .map(([categoria, activos]) => ({
        categoria,
        activos: activos.sort((a, b) => {
          const pa = AjustesComponent.PRIORIDAD_ACTIVO[a] ?? 99;
          const pb = AjustesComponent.PRIORIDAD_ACTIVO[b] ?? 99;
          return pa !== pb ? pa - pb : a.localeCompare(b);
        }),
      }));
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
