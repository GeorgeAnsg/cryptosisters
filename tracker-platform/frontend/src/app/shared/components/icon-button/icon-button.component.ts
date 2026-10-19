import { Component, input, output } from '@angular/core';
import { Button } from 'primeng/button';

export type TamanoIconButton = 'sm' | 'lg';

// boton circular -- UN solo sitio para todo boton-icono de la app (campana,
// refrescar, cambiar orden...). El aspecto (fondo blanco, borde, hover
// negro) se fija UNA vez en el tema global (app.config.ts, severity
// "secondary", variante normal -- NO "outlined", que en PrimeNG es siempre
// fondo transparente), no aqui con clases sueltas.
// 'sm' = botones de filtro, como .btn-icono-redondo (32px) en la app vieja.
// 'lg' = acciones de cabecera, como .btn-campana (48px) en la app vieja.
@Component({
  selector: 'app-icon-button',
  standalone: true,
  imports: [Button],
  template: ` <p-button [icon]="icon()" [rounded]="true" severity="secondary" [size]="tamano() === 'lg' ? 'large' : 'small'" (onClick)="clicked.emit()" /> `,
})
export class IconButtonComponent {
  icon = input.required<string>();
  tamano = input<TamanoIconButton>('sm');
  clicked = output<void>();
}
