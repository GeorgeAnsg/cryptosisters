import { Component, computed, input, output } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ToggleSwitch } from 'primeng/toggleswitch';
import { BadgeComponent, VarianteBadge } from '../badge/badge.component';
import { CategoriaMercado, Trader } from '../../models/trader';
import { colorTrader } from '../../utils/color-trader';

const VARIANTE_ESTILO: Record<Trader['estilo'], VarianteBadge> = {
  posicional: 'accent',
  activo: 'accent',
  muy_activo: 'warn',
};
const VARIANTE_RIESGO: Record<Trader['riesgo'], VarianteBadge> = {
  conservador: 'ok',
  moderado: 'warn',
  agresivo: 'bad',
};
const CLASE_CATEGORIA: Record<CategoriaMercado, string> = {
  Cripto: 'bg-cat-cripto',
  Acción: 'bg-cat-accion',
  'Materia prima': 'bg-cat-materia-prima',
  Divisa: 'bg-cat-divisa',
  Índice: 'bg-cat-indice',
};

// tarjeta de trader -- equivalente a la funcion tarjeta() de
// backend/static/index.html. Recibe un Trader y emite cuando el usuario
// toca el interruptor de seguir/dejar de seguir; no sabe nada de la lista
// que la contiene.
@Component({
  selector: 'app-trader-card',
  standalone: true,
  imports: [BadgeComponent, DecimalPipe, FormsModule, ToggleSwitch],
  templateUrl: './trader-card.component.html',
})
export class TraderCardComponent {
  trader = input.required<Trader>();
  seguirCambiado = output<boolean>();

  protected readonly colorTrader = colorTrader;
  protected readonly VARIANTE_ESTILO = VARIANTE_ESTILO;
  protected readonly VARIANTE_RIESGO = VARIANTE_RIESGO;
  protected readonly CLASE_CATEGORIA = CLASE_CATEGORIA;

  protected readonly inicial = computed(() => this.trader().nombre.charAt(0));
  protected readonly direccionCorta = computed(() => {
    const a = this.trader().address;
    return `${a.slice(0, 8)}…${a.slice(-4)}`;
  });
}
