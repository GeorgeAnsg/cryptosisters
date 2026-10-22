// mismo alias que ALIAS_MONEDA en el backend (hyperliquid.py) -- las
// variantes "apalancadas"/wrapped de Hyperliquid son la misma moneda a
// efectos de filtros (BTC/UBTC, etc.), aqui hace falta repetirlo porque
// posicionActual/holdingsSpot llegan con el simbolo crudo, sin alias
const ALIAS_MONEDA: Record<string, string> = { UBTC: 'BTC', UETH: 'ETH', USOL: 'SOL' };

export function etiquetaMoneda(coin: string): string {
  return ALIAS_MONEDA[coin] ?? coin;
}
