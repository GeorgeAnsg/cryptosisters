import { ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { providePrimeNG } from 'primeng/config';
import { definePreset } from '@primeng/themes';
import Aura from '@primeng/themes/aura';
import { provideFirebaseApp, initializeApp } from '@angular/fire/app';
import { provideAuth, getAuth } from '@angular/fire/auth';

import { routes } from './app.routes';
import { loadingInterceptor } from './core/loading/loading.interceptor';
import { authInterceptor } from './core/auth/auth.interceptor';
import { environment } from '../environments/environment';

// tema global de PrimeNG, UN solo sitio para que todos los componentes
// (select, input, boton, toggle...) compartan radio y color -- en vez de
// parchear cada componente con clases sueltas, que es lo que fallaba antes.
// primary en negro (no el verde de Aura por defecto): es el color de acento
// que ya usa el resto de la app (interruptores, pestañas activas, botones
// redondos) en backend/static/index.html.
//
// OJO: el radio "9999px" NO va en el primitivo global -- primitive.borderRadius
// lo reutilizan tambien los paneles flotantes (dropdown del select, overlay
// del datepicker, etc.), asi que ponerlo ahi los deja circulares. El pill
// solo se aplica a nivel de componente (formField, button), que es donde
// vive de verdad en la app vieja (.control-redondo, .btn-icono-redondo).
const RADIO_PILL = '9999px';

const CorvusPreset = definePreset(Aura, {
  semantic: {
    primary: {
      50: '#f4f4f5',
      100: '#e4e4e7',
      200: '#d4d4d8',
      300: '#a1a1aa',
      400: '#71717a',
      500: '#131417',
      600: '#0f1013',
      700: '#0c0d0f',
      800: '#09090b',
      900: '#060607',
      950: '#030303',
    },
    // formField.borderRadius es el token que leen inputtext/select/button
    // (y por tanto app-icon-button); overlay.select/popover/modal usan su
    // propio token aparte y se quedan con el radio normal de Aura (no pill)
    formField: {
      borderRadius: RADIO_PILL,
    },
    colorScheme: {
      light: {
        // borde de TODO input/select -- literal var(--border) de la app
        // vieja (control-redondo), no el gris oscuro que trae Aura por
        // defecto (surface.300, mucho mas visible de lo que teniamos)
        formField: {
          borderColor: 'var(--border)',
          hoverBorderColor: 'var(--border)',
          focusBorderColor: 'var(--fg-muted)', // igual que .control-redondo:focus
        },
      },
    },
  },
  components: {
    // boton-icono (campana, refrescar, orden) = severity="secondary" --
    // aqui se fija su aspecto UNA vez para que coincida con
    // .btn-icono-redondo de la app vieja: fondo blanco, borde tenue, icono
    // gris, hover negro con texto blanco. IMPORTANTE: es la variante "root"
    // (boton normal), NO "outlined" -- outlined en PrimeNG es SIEMPRE fondo
    // transparente por diseño (ignora el token "background"), así que con
    // fondo blanco de pagina gris clara (--bg) el borde pálido se volvía
    // invisible. "root" sí pinta el fondo de verdad.
    button: {
      colorScheme: {
        light: {
          root: {
            secondary: {
              background: 'var(--panel)',
              hoverBackground: 'var(--panel-dark)',
              activeBackground: 'var(--panel-dark)',
              borderColor: 'var(--border)',
              hoverBorderColor: 'var(--panel-dark)',
              activeBorderColor: 'var(--panel-dark)',
              color: 'var(--fg-muted)',
              hoverColor: '#ffffff',
              activeColor: '#ffffff',
            },
          },
        },
      },
    },
  },
});

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(withInterceptors([loadingInterceptor, authInterceptor])),
    provideAnimationsAsync(),
    providePrimeNG({
      theme: {
        preset: CorvusPreset,
        options: { darkModeSelector: '.dark' },
      },
    }),
    provideFirebaseApp(() => initializeApp(environment.firebase)),
    provideAuth(() => getAuth()),
  ],
};
