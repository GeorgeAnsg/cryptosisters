import { Component, input, model } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { InputText } from 'primeng/inputtext';

// UN solo sitio para todo input de texto suelto de la app (no los que ya
// vienen envueltos en su propio componente PrimeNG, como p-password o
// p-inputnumber) -- mismo patron que app-icon-button: envuelve pInputText
// para fijar aqui el aspecto (tamaño de letra) una vez, en vez de repetir
// "text-sm" en cada formulario que necesite un input.
@Component({
  selector: 'app-input-text',
  standalone: true,
  imports: [FormsModule, InputText],
  template: `
    <input
      pInputText
      class="w-full !text-sm"
      [type]="type()"
      [placeholder]="placeholder()"
      [autocomplete]="autocomplete()"
      [(ngModel)]="valor"
    />
  `,
})
export class InputTextComponent {
  type = input('text');
  placeholder = input('');
  autocomplete = input('off');
  valor = model('');
}
