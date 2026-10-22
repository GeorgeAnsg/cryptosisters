import { Component, computed, inject } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { Button } from 'primeng/button';
import { FreldiScoreItem, FreldiService } from '../../core/freldi/freldi.service';

interface TarjetaComponente {
  clave: string;
  titulo: string;
  subtitulo: string;
  score10: number;
  label: string;
  rationale: string;
}

const DEFS: Array<{ clave: keyof import('../../core/freldi/freldi.service').FreldiScores; titulo: string; subtitulo: string }> = [
  { clave: 'F', titulo: 'F', subtitulo: 'Fear & Greed' },
  { clave: 'R', titulo: 'R', subtitulo: 'RSI' },
  { clave: 'E', titulo: 'E', subtitulo: 'EMA 200' },
  { clave: 'L', titulo: 'L', subtitulo: 'Liquidez' },
  { clave: 'D', titulo: 'D', subtitulo: 'Dólar (DXY)' },
  { clave: 'I', titulo: 'I', subtitulo: 'Interés' },
  { clave: 'X', titulo: 'X', subtitulo: 'VIX' },
];

const ETIQUETA_SEÑAL: Record<string, string> = {
  strong_buy: 'Compra fuerte',
  buy: 'Compra',
  neutral: 'Neutral',
  sell: 'Venta',
  strong_sell: 'Venta fuerte',
};

// pestaña "Freldi" -- muestra el indice FRELDI(X) que ya calcula Multivac
// (otra app del usuario), traido por el backend una vez al dia (ver
// FreldiService/backend/freldi.py). Version simplificada del original
// (Desktop/new/Trading/freldi): mismos datos, con el estilo de Corvus.
@Component({
  selector: 'app-freldi',
  standalone: true,
  imports: [DecimalPipe, DatePipe, Button],
  templateUrl: './freldi.component.html',
})
export class FreldiComponent {
  protected readonly freldi = inject(FreldiService);

  constructor() {
    this.freldi.refrescar();
  }

  protected readonly tarjetas = computed<TarjetaComponente[]>(() => {
    const scores = this.freldi.datos()?.scores;
    if (!scores) return [];
    return DEFS.map((d) => {
      const it = (scores[d.clave] as FreldiScoreItem) ?? { score10: 0, label: 'N/A', rationale: 'Sin datos' };
      return { clave: d.clave, titulo: d.titulo, subtitulo: d.subtitulo, score10: it.score10, label: it.label, rationale: it.rationale };
    });
  });

  protected readonly total100 = computed(() => this.freldi.datos()?.scores?.total100 ?? null);

  protected readonly etiquetaTotal = computed(() => {
    const t = this.total100();
    if (t == null) return '—';
    if (t >= 80) return 'Acumulación fuerte';
    if (t >= 65) return 'Acumulación';
    if (t >= 50) return 'Neutral';
    if (t >= 35) return 'Distribución';
    return 'Distribución fuerte';
  });

  protected readonly etiquetaSenal = computed(() => {
    const s = this.freldi.datos()?.scores?.buySignal ?? '';
    return ETIQUETA_SEÑAL[s] ?? s;
  });

  protected barraPct(score10: number): number {
    return Math.max(0, Math.min(100, score10 * 10));
  }

  // aviso cuando Multivac sirve algun dato cacheado/caido -- mismo criterio
  // que la pagina original de Multivac (status degradado, o alguna fuente != 'ok')
  protected readonly hayAvisoDatos = computed(() => {
    const snap = this.freldi.datos();
    if (!snap) return false;
    if (snap.status === 'degraded') return true;
    const h = snap.sourcesHealth;
    return !!h && Object.values(h).some((x) => x?.status && x.status !== 'ok');
  });

  protected readonly fuentesAfectadas = computed(() => {
    const h = this.freldi.datos()?.sourcesHealth;
    if (!h) return '';
    return Object.entries(h)
      .filter(([, v]) => v?.status && v.status !== 'ok')
      .map(([k, v]) => {
        const edad = typeof v.ageHours === 'number' ? `${Math.round(v.ageHours)}h` : null;
        const cola = [edad, (v.message || '').trim()].filter(Boolean).join(' · ');
        return cola ? `${k} (${v.status} · ${cola})` : `${k} (${v.status})`;
      })
      .join(' · ');
  });
}
