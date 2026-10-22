// mismo alias que ALIAS_MONEDA en el backend (hyperliquid.py) -- las
// variantes "apalancadas"/wrapped de Hyperliquid son la misma moneda a
// efectos de filtros (BTC/UBTC, etc.), aqui hace falta repetirlo porque
// posicionActual/holdingsSpot llegan con el simbolo crudo, sin alias
const ALIAS_MONEDA: Record<string, string> = { UBTC: 'BTC', UETH: 'ETH', USOL: 'SOL' };

export function etiquetaMoneda(coin: string): string {
  // "xyz2:SP500", "hyna:BTC"... el prefijo es de que builder-dex (HIP-3)
  // lista ese mercado -- igual que etiqueta_moneda() en el backend, nunca
  // es info util para quien lo ve
  const base = coin.includes(':') ? coin.split(':')[1] : coin;
  return ALIAS_MONEDA[base] ?? base;
}
