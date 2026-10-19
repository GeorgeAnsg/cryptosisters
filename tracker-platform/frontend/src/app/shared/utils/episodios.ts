// Porte literal de agruparEpisodios/construirBloques/marcarCierres en
// backend/static/index.html (la app vieja) -- NO simplificar esta logica,
// ya se intento una vez y perdio justo lo que hacia utiles estas tablas
// (el historial completo abierta/cerrada por bloques en trading, el listado
// plano de todas las compras/ventas en spot). Opera sobre operacionesRecientes
// (fills crudos de Hyperliquid, mas reciente primero -- ver hyperliquid.py
// obtener_fills) tal cual la expone /candidatos.

export interface FillCrudo {
  coin: string;
  lado: 'Long' | 'Short' | 'Spot' | '';
  accion: 'Abre' | 'Cierra' | '';
  px: number;
  sz: number;
  notional: number;
  time: string;
  ts: number;
  closedPnl: number;
}

export interface Episodio extends FillCrudo {
  nFills?: number;
}

export interface Bloque {
  coin: string;
  lado: 'Long' | 'Short' | 'Spot' | '';
  filas: Episodio[];
  neto: number;
  totalAbierto: number;
  abierta: boolean;
  truncada: boolean;
}

export interface FilaConCierre extends Episodio {
  cierraDelTodo: boolean;
  esInicio: boolean;
}

// el exchange parte una sola decision en muchos fills pequeños ejecutados
// en el mismo minuto; se agrupan por moneda+lado+accion+minuto en una sola fila
export function agruparEpisodios(ops: FillCrudo[]): Episodio[] {
  const grupos: Episodio[] = [];
  const indice = new Map<string, number>();
  for (const o of ops) {
    const clave = `${o.coin}|${o.lado}|${o.accion}|${o.time}`;
    let idx = indice.get(clave);
    if (idx == null) {
      idx = grupos.length;
      indice.set(clave, idx);
      grupos.push({ coin: o.coin, lado: o.lado, accion: o.accion, time: o.time, ts: o.ts, sz: 0, notional: 0, closedPnl: 0, nFills: 0, px: 0 });
    }
    const g = grupos[idx];
    g.sz += o.sz;
    g.notional += o.notional || 0;
    g.closedPnl += o.closedPnl || 0;
    g.nFills = (g.nFills ?? 0) + 1;
  }
  return grupos.map((g) => ({
    ...g,
    sz: Number(g.sz.toPrecision(8)),
    notional: Math.round(g.notional),
    closedPnl: Number(g.closedPnl.toFixed(2)),
    px: g.sz ? Number((g.notional / g.sz).toPrecision(6)) : 0,
  }));
}

// ops viene de mas reciente a mas antigua; se procesa en orden cronologico
// para detectar rachas de "ir añadiendo/reduciendo la misma posicion" por
// moneda+lado, de forma que no se interrumpan visualmente con operaciones
// de otras monedas.
export function construirBloques(ops: Episodio[]): Bloque[] {
  const cronologico = [...ops].reverse();
  const bloques: Bloque[] = [];
  const abiertoPorClave = new Map<string, number>();
  for (const o of cronologico) {
    if (o.lado !== 'Long' && o.lado !== 'Short' && o.lado !== 'Spot') {
      bloques.push({ coin: o.coin, lado: '', filas: [o], neto: 0, totalAbierto: 0, abierta: false, truncada: false });
      continue;
    }
    const clave = `${o.coin}|${o.lado}`;
    let idx = abiertoPorClave.get(clave);
    if (idx == null) {
      idx = bloques.length;
      // si el primer movimiento que vemos de esta posicion ya es un
      // "Cierra", es que la posicion existia antes de lo que tenemos en
      // estos datos: no sabemos su tamaño real, solo lo que cambia desde aqui.
      bloques.push({ coin: o.coin, lado: o.lado, filas: [], neto: 0, totalAbierto: 0, abierta: true, truncada: o.accion === 'Cierra' });
      abiertoPorClave.set(clave, idx);
    }
    const b = bloques[idx];
    b.filas.push(o);
    if (o.accion === 'Abre') b.totalAbierto = Number((b.totalAbierto + o.sz).toPrecision(8));
    b.neto = Number((b.neto + (o.accion === 'Abre' ? o.sz : -o.sz)).toPrecision(8));
    if (Math.abs(b.neto) < 0.00001) {
      b.abierta = false;
      abiertoPorClave.delete(clave);
    }
  }
  return bloques.reverse(); // mas reciente primero
}

// filas tiene que venir en orden cronologico (mas antigua primero). Un
// "Cierra" solo es un cierre DE VERDAD si, tras restarle su tamaño a lo que
// quedaba, no queda nada (o casi); si queda algo, es una reduccion parcial y
// la posicion sigue viva.
export function marcarCierres(filas: Episodio[]): FilaConCierre[] {
  let restante = 0;
  return filas.map((o, i) => {
    restante += o.accion === 'Abre' ? o.sz : -o.sz;
    const cierraDelTodo = o.accion === 'Cierra' && Math.abs(restante) < 0.00001;
    return { ...o, cierraDelTodo, esInicio: i === 0 };
  });
}
