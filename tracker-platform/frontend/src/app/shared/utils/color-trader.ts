// color pastel determinista a partir de la direccion -- mismo trader,
// mismo color, en cualquier sitio donde aparezca (tarjeta, tabla de
// posiciones, chip pequeño...). Un solo sitio para la formula.
export function colorTrader(address: string): string {
  return `hsl(${(address.charCodeAt(2) * 37) % 360}, 45%, 58%)`;
}
