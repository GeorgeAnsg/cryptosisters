// "hace 5 minutos" / "hace 2h" / "hace 3d" -- misma idea que
// fechaRelativaCorta() en la app vieja. Un solo sitio para no repetir el
// calculo en cada feature que muestra timestamps relativos (consenso,
// dashboard...).
export function tiempoRelativo(fechaIso: string): string {
  const diffMs = Date.now() - new Date(fechaIso).getTime();
  const minutos = Math.round(diffMs / 60_000);
  if (minutos < 1) return 'hace un momento';
  if (minutos < 60) return `hace ${minutos} minuto${minutos === 1 ? '' : 's'}`;
  const horas = Math.round(minutos / 60);
  if (horas < 24) return `hace ${horas}h`;
  return `hace ${Math.round(horas / 24)}d`;
}
