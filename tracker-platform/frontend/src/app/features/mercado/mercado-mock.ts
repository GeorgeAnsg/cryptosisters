export interface FilaMercadoTrading {
  coin: string;
  nLong: number;
  nShort: number;
  dLong: number;
  dShort: number;
}

export interface FilaMercadoSpot {
  coin: string;
  n: number;
  d: number;
}

// datos de mentira por ahora -- en la app vieja esto salia de agregar
// posicion_actual/holdings_spot de TODOS los candidatos guardados (vista
// de mercado, no de tu cartera). Se sustituira por la agregacion real del
// backend sin tocar el componente, solo esta fuente.
export const MERCADO_TRADING_MOCK: FilaMercadoTrading[] = [
  { coin: 'BTC', nLong: 14, nShort: 5, dLong: 420_000, dShort: 95_000 },
  { coin: 'HYPE', nLong: 9, nShort: 3, dLong: 180_000, dShort: 40_000 },
  { coin: 'ETH', nLong: 7, nShort: 8, dLong: 150_000, dShort: 165_000 },
  { coin: 'SOL', nLong: 6, nShort: 2, dLong: 95_000, dShort: 18_000 },
  { coin: 'XRP', nLong: 2, nShort: 6, dLong: 22_000, dShort: 70_000 },
  { coin: 'LTC', nLong: 1, nShort: 0, dLong: 8_000, dShort: 0 },
];

export const MERCADO_SPOT_MOCK: FilaMercadoSpot[] = [
  { coin: 'BTC', n: 18, d: 610_000 },
  { coin: 'ETH', n: 12, d: 240_000 },
  { coin: 'HYPE', n: 10, d: 150_000 },
  { coin: 'SOL', n: 8, d: 85_000 },
  { coin: 'SP500', n: 6, d: 120_000 },
  { coin: 'GOLD', n: 5, d: 60_000 },
];
