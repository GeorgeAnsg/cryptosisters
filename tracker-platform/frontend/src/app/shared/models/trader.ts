export type Estilo = 'posicional' | 'activo' | 'muy_activo';
export type Riesgo = 'conservador' | 'moderado' | 'agresivo';
export type CategoriaMercado = 'Cripto' | 'Acción' | 'Materia prima' | 'Divisa' | 'Índice';

export interface MonedaOperada {
  nombre: string;
  categoria: CategoriaMercado;
}

// un trader candidato tal como lo muestra la tarjeta -- mismos campos que
// backend/static/index.html (la app vieja), para que el port del backend
// real no tenga que cambiar la forma de los datos
export interface Trader {
  address: string;
  nombre: string;
  puntuacion: number | null;
  estilo: Estilo;
  riesgo: Riesgo;
  antiguedadDias: number;
  drawdown: number | null;
  cuenta: number;
  winRate: number | null;
  retornoPct: number | null;
  profitFactor: number | null;
  siguiendo: boolean;
  monedas: MonedaOperada[];
  // apuesta curada a mano, nunca juzgada por backtest -- por eso puede
  // puntuacion==null y aun debe aparecer en el listado (ver traders.component.ts)
  esEspeculativo: boolean;
  // si el ciclo de descubrimiento lo desestimo del pool (ya no pasa el
  // filtro de calidad) -- dispara notificacion a quien lo siga
  desestimado?: { motivo: string; fecha: string };
}
