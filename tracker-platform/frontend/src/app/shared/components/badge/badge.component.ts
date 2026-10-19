import { Component, computed, input } from '@angular/core';

export type VarianteBadge = 'accent' | 'ok' | 'warn' | 'bad' | 'neutral';

// pastilla de color reutilizable -- estilo/riesgo del trader, categoria de
// mercado (cripto/accion/...), lo que sea. Equivalente a .badge en la app
// vieja, con las mismas variantes de color (b-activo, b-agresivo...).
const CLASES_VARIANTE: Record<VarianteBadge, string> = {
  accent: 'bg-accent-weak text-accent',
  ok: 'bg-ok-bg text-ok',
  warn: 'bg-warn-bg text-warn',
  bad: 'bg-bad-bg text-bad',
  neutral: 'bg-border text-fg-muted',
};

@Component({
  selector: 'app-badge',
  standalone: true,
  template: `
    <span
      class="inline-block rounded-pill px-2 py-0.5 text-[12px] font-semibold uppercase tracking-wide"
      [class]="CLASES_VARIANTE[variante()]"
    >
      <ng-content />
    </span>
  `,
})
export class BadgeComponent {
  variante = input<VarianteBadge>('neutral');
  protected readonly CLASES_VARIANTE = CLASES_VARIANTE;
}
