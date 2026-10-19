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
}
