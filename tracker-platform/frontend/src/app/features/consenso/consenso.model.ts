export interface ConsensoTrader {
  nombre: string;
  address: string;
  fecha: string;
  invertidoUsd: number;
  precio: number;
  pnlPct: number | null;
}

export interface GrupoConsenso {
  coin: string;
  lado: 'Long' | 'Short';
  verbo: 'han entrado' | 'han cerrado';
  traders: ConsensoTrader[];
}

// fecha que se muestra a la derecha del titulo de cada grupo -- igual que
// infoConsenso() en la app vieja (el segundo mas antiguo, no el ultimo: el
// momento en que el grupo "ya era un grupo", no el ultimo que se sumo)
export function fechaGrupo(traders: ConsensoTrader[]): string {
  const ordenadas = [...traders].map((t) => t.fecha).sort();
  return ordenadas[Math.min(1, ordenadas.length - 1)];
}
