import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { ProgressSpinner } from 'primeng/progressspinner';
import { LoadingService } from './core/loading/loading.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, ProgressSpinner],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {
  protected readonly loading = inject(LoadingService);
}
