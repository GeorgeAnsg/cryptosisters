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

// equivalente a gruposEntrando/gruposCerrando en calcularSeguimiento() de
// la app vieja: varios traders independientes haciendo lo MISMO (misma
// moneda+direccion) en las ultimas 72h -- mas señal que uno solo. Datos de
// mentira por ahora -- el agrupado real necesita el historial completo de
// movimientos (alertas), que este rebuild todavia no tiene.
export const CONSENSO_MOCK: GrupoConsenso[] = [
  {
    coin: 'BTC',
    lado: 'Long',
    verbo: 'han entrado',
    traders: [
      { nombre: 'Lavanda', address: '0xe19813a1f2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7', fecha: '2026-10-19T04:00:00Z', invertidoUsd: 18_500, precio: 67_240, pnlPct: 1.8 },
      { nombre: 'Begonia', address: '0x12443e7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e', fecha: '2026-10-19T01:00:00Z', invertidoUsd: 4_200, precio: 66_980, pnlPct: 2.4 },
      { nombre: 'Romero', address: '0x3b9f49a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7', fecha: '2026-10-18T21:00:00Z', invertidoUsd: 9_800, precio: 66_500, pnlPct: 0.6 },
    ],
  },
  {
    coin: 'ETH',
    lado: 'Short',
    verbo: 'han cerrado',
    traders: [
      { nombre: 'Acacia', address: '0xd908ba2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e', fecha: '2026-10-19T05:00:00Z', invertidoUsd: 9_800, precio: 3_195, pnlPct: null },
      { nombre: 'Olivo', address: '0x0fe2695f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d', fecha: '2026-10-19T02:00:00Z', invertidoUsd: 6_100, precio: 3_210, pnlPct: null },
    ],
  },
];
