// un movimiento dentro de una posicion -- Abre (inicio)/Añade/Reduce/Cierra
// en trading, Compra (inicio)/Compra/Vende/Cierra en spot. Lo que se ve al
// desplegar la flechita de una fila, igual que en la app vieja.
export interface MovimientoPosicion {
  fecha: string;
  verbo: string;
  notionalUsd: number;
  precio: number;
  pnlUsd: number | null;
  // coin/lado solo los trae el backend real (ver candidatos.service.ts),
  // para poder repartir el historial de un trader entre sus distintas
  // posiciones abiertas -- un mock de una sola posicion no los necesitaba
  coin?: string;
  lado?: 'Long' | 'Short';
}

export interface PosicionTrading {
  fecha: string;
  lado: 'Long' | 'Short';
  coin: string;
  invertidoUsd: number;
  cuentaTrader: number;
  entrada: number;
  // precio actual real del activo (valorPosicion/tamaño) -- para calcular el
  // % en vivo de lo que el USUARIO invirtio a SU propio precio de entrada,
  // no al del trader (ver MisPosicionesService.pctEnVivo)
  precioActual: number;
  takeProfit: number | null;
  stopLoss: number | null;
  traderAddress: string;
  traderNombre: string;
  resultadoUsd: number | null;
  // solo si hay mas de un movimiento -- una posicion con uno solo no tiene
  // nada que desplegar (ver tieneDetalle en la app vieja)
  movimientos?: MovimientoPosicion[];
}

export interface PosicionSpot {
  fecha: string;
  coin: string;
  invertidoUsd: number;
  cuentaTrader: number;
  traderAddress: string;
  traderNombre: string;
  valorActualUsd: number;
  // precio actual real (valorActual/tamaño) -- ver PosicionTrading.precioActual
  precioActual: number;
  resultadoUsd: number | null;
  movimientos?: MovimientoPosicion[];
}
