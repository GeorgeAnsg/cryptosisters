import { Component } from '@angular/core';

interface CampoCribado {
  etiqueta: string;
  valor: string;
  explicacion: string;
}

interface GrupoCribado {
  grupo: string;
  campos: CampoCribado[];
}

// valores REALES de las constantes que usa el backend para descubrir y
// mantener candidatos (scripts/descubrimiento.py / hyperliquid.py), tal
// cual CRIBADO_CAMPOS en la app vieja (backend/static/index.html). Solo
// consulta -- los campos van deshabilitados porque tocarlos aqui no
// cambia nada todavia, falta exponerlos por API para que sea editable.
const GRUPOS: GrupoCribado[] = [
  {
    grupo: 'Preselección del leaderboard (antes de gastar backtests)',
    campos: [
      { etiqueta: 'Cuenta mínima', valor: '$10.000', explicacion: 'Por debajo de esto no hay suficiente "piel en el juego" -- se descarta directamente.' },
      {
        etiqueta: 'Techo de cuenta',
        valor: '(sin techo)',
        explicacion: 'Antes había un máximo de $5M ("ballena no replicable"); se quitó porque descartaba 785 cuentas buenas de golpe sin mirar nada más.',
      },
      {
        etiqueta: 'ROI mínimo del mes',
        valor: '5%',
        explicacion: 'Preselección rápida con el ROI del último mes que ya trae el leaderboard, sin pedir nada más a Hyperliquid.',
      },
      {
        etiqueta: 'Consistencia exigida',
        valor: 'ROI semana > 0% Y ROI mes ≥ 5% Y ROI histórico > 0%',
        explicacion: 'Un solo mes bueno es ruido (puede ser suerte en una moneda volátil) -- se exigen las tres ventanas en positivo para favorecer consistencia sobre un pico aislado.',
      },
      {
        etiqueta: 'Candidatos evaluados por ciclo',
        valor: '(sin techo -- todos los que pasen la preselección, ~2-3 mil)',
        explicacion:
          'El ciclo es semanal y ya no se pierde información por rate limit (reintento sin límite), así que se evalúan TODOS los que pasen la preselección, por lento que sea.',
      },
    ],
  },
  {
    grupo: 'Backtest (para que una racha cuente como puntuación real)',
    campos: [
      { etiqueta: 'Cierres mínimos para puntuar', valor: '10', explicacion: 'Menos que esto es una muestra demasiado pequeña -- una buena o mala racha domina el resultado.' },
      { etiqueta: 'Días de historial mínimos', valor: '30', explicacion: 'Hace falta verlo operar en más de una sola racha o sesión, no solo "tuvo una buena tarde".' },
      {
        etiqueta: 'Días máximos de inactividad',
        valor: '21',
        explicacion: 'Si su último cierre es más viejo que esto, ya no está operando ahora -- un historial genial de hace meses no sirve para copiarlo hoy.',
      },
      { etiqueta: 'Umbral de veto catastrófico', valor: '-15%', explicacion: 'Retorno por debajo de esto descalifica esa faceta (trading o spot) del todo, aunque la otra vaya genial.' },
      {
        etiqueta: 'Notional mínimo en spot',
        valor: '$10',
        explicacion: 'Ventas de shitcoins en céntimos (polvo/airdrops) no cuentan como operación real -- inflarían el win rate sin representar capital de verdad.',
      },
    ],
  },
  {
    grupo: 'Puntuación final (0-100, umbral de entrada 70)',
    campos: [
      { etiqueta: 'Peso del retorno', valor: '40%', explicacion: 'p_retorno = 50 + retorno_pct, recortado a [0,100].' },
      { etiqueta: 'Peso del profit factor', valor: '30%', explicacion: 'p_pf = profit_factor × 10, recortado a [0,100] (ganancia bruta entre pérdida bruta).' },
      { etiqueta: 'Peso del drawdown', valor: '30%', explicacion: 'p_dd = 100 + drawdown_pct × 2, recortado a [0,100] -- penaliza caídas grandes desde el pico.' },
      { etiqueta: 'Puntuación mínima para descubrir', valor: '70', explicacion: 'Umbral para considerarlo un descubrimiento real (en trading o en spot).' },
      {
        etiqueta: 'Puntuación mínima para mantener',
        valor: '50',
        explicacion: 'Más baja que la de descubrir, para no dejar de seguir a alguien por una mala racha puntual (histéresis).',
      },
    ],
  },
];

@Component({
  selector: 'app-cribado',
  standalone: true,
  templateUrl: './cribado.component.html',
})
export class CribadoComponent {
  protected readonly grupos = GRUPOS;
}
