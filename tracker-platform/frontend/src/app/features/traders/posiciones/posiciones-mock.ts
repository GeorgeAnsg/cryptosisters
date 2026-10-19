// un movimiento dentro de una posicion -- Abre (inicio)/Añade/Reduce/Cierra
// en trading, Compra (inicio)/Compra/Vende/Cierra en spot. Lo que se ve al
// desplegar la flechita de una fila, igual que en la app vieja.
export interface MovimientoPosicion {
  fecha: string;
  verbo: string;
  notionalUsd: number;
  precio: number;
  pnlUsd: number | null;
}

export interface PosicionTrading {
  fecha: string;
  lado: 'Long' | 'Short';
  coin: string;
  invertidoUsd: number;
  cuentaTrader: number;
  entrada: number;
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
  resultadoUsd: number | null;
  movimientos?: MovimientoPosicion[];
}

// equivalente a tablaTradingCompletaHtml / tablaSpotCompletaHtml en la app
// vieja (calcularSeguimiento(), backend/static/index.html): las posiciones
// ABIERTAS de los traders que sigues, no un resumen de su ficha. Datos de
// mentira por ahora -- el backend real las saca de posicion_actual/
// holdings_spot de cada candidato seguido (sigue_trading/sigue_spot).
//
// Simplificado respecto a la app vieja: de momento sin historial de
// movimientos expandible (Abre/Añade/Reduce/Cierra), sin la caja de
// "Consenso reciente" (varios traders coincidiendo en la misma jugada) y
// sin el botón "Abrir" conectado a copiar la posición -- eso depende de
// estado que todavía no existe en este rebuild (bloques de movimientos,
// alertas, "mis posiciones").
export const POSICIONES_TRADING_MOCK: PosicionTrading[] = [
  {
    fecha: '2026-10-18T09:14:00Z',
    lado: 'Long',
    coin: 'BTC',
    invertidoUsd: 18_500,
    cuentaTrader: 105_292,
    entrada: 67_240,
    takeProfit: 72_000,
    stopLoss: 64_000,
    traderAddress: '0xe19813a1f2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7',
    traderNombre: 'Lavanda',
    resultadoUsd: 1_240,
    movimientos: [
      { fecha: '2026-10-16T10:02:00Z', verbo: 'Abre (inicio)', notionalUsd: 12_000, precio: 64_800, pnlUsd: null },
      { fecha: '2026-10-18T09:14:00Z', verbo: 'Añade', notionalUsd: 6_500, precio: 67_900, pnlUsd: null },
    ],
  },
  {
    fecha: '2026-10-17T22:40:00Z',
    lado: 'Short',
    coin: 'ETH',
    invertidoUsd: 9_800,
    cuentaTrader: 52_552,
    entrada: 3_180,
    takeProfit: 2_950,
    stopLoss: 3_320,
    traderAddress: '0xd908ba2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e',
    traderNombre: 'Acacia',
    resultadoUsd: -210,
    movimientos: [
      { fecha: '2026-10-15T08:20:00Z', verbo: 'Abre (inicio)', notionalUsd: 11_000, precio: 3_210, pnlUsd: null },
      { fecha: '2026-10-17T22:40:00Z', verbo: 'Reduce', notionalUsd: 1_200, precio: 3_195, pnlUsd: 38 },
    ],
  },
  {
    fecha: '2026-10-17T14:05:00Z',
    lado: 'Long',
    coin: 'HYPE',
    invertidoUsd: 4_200,
    cuentaTrader: 12_938,
    entrada: 28.4,
    takeProfit: null,
    stopLoss: 24.0,
    traderAddress: '0x12443e7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e',
    traderNombre: 'Begonia',
    resultadoUsd: 380,
  },
  {
    fecha: '2026-10-16T08:51:00Z',
    lado: 'Long',
    coin: 'SOL',
    invertidoUsd: 15_600,
    cuentaTrader: 158_954,
    entrada: 142.1,
    takeProfit: 165,
    stopLoss: 130,
    traderAddress: '0x3b9f49a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7',
    traderNombre: 'Romero',
    resultadoUsd: null,
  },
];

export const POSICIONES_SPOT_MOCK: PosicionSpot[] = [
  {
    fecha: '2026-10-18T07:30:00Z',
    coin: 'BTC',
    invertidoUsd: 22_000,
    cuentaTrader: 105_292,
    traderAddress: '0xe19813a1f2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7',
    traderNombre: 'Lavanda',
    valorActualUsd: 23_410,
    resultadoUsd: 1_410,
    movimientos: [
      { fecha: '2026-10-10T07:00:00Z', verbo: 'Compra (inicio)', notionalUsd: 15_000, precio: 61_200, pnlUsd: null },
      { fecha: '2026-10-18T07:30:00Z', verbo: 'Compra', notionalUsd: 7_000, precio: 65_800, pnlUsd: null },
    ],
  },
  {
    fecha: '2026-10-15T19:12:00Z',
    coin: 'SP500',
    invertidoUsd: 6_500,
    cuentaTrader: 52_552,
    traderAddress: '0xd908ba2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e',
    traderNombre: 'Acacia',
    valorActualUsd: 6_120,
    resultadoUsd: -380,
  },
  {
    fecha: '2026-10-14T11:00:00Z',
    coin: 'SUI',
    invertidoUsd: 3_100,
    cuentaTrader: 158_954,
    traderAddress: '0x3b9f49a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7',
    traderNombre: 'Romero',
    valorActualUsd: 3_640,
    resultadoUsd: 540,
  },
];
