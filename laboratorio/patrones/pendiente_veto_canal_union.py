"""
Tercer intento de arreglar el defecto de XRP en el veto de canal (17-sept-2026),
tras `pendiente_veto_canal.py` (umbral ABSOLUTO 0.5, adoptado -- BTC p=0.015,
XRP p=0.355) y `pendiente_veto_canal_percentil.py` (percentil RELATIVO por
moneda, ventana=20/percentil=0.5, descartado -- BTC p=0.270, XRP p=0.113).

Los dos intentos anteriores SUSTITUYEN un criterio por otro. Este prueba
algo no intentado todavia: COMBINARLOS con un OR -- un canal cuenta como
"tendencia confirmada" si pasa el umbral absoluto (0.5, calibrado en ETH)
O el percentil relativo de su propia moneda (ventana=20, percentil=0.5,
tambien calibrado en ETH). Es una eleccion ESTRUCTURAL (que funcion de
agregacion usar), no un numero nuevo tuneado en BTC/XRP -- los dos
umbrales de entrada ya estaban fijados de antemano por sus propias
investigaciones en ETH, aqui solo se cambia como se combinan.

Motivacion: el percentil relativo existe precisamente para no penalizar a
XRP (sus canales ascendentes puntuan sistematicamente peor que los de
ETH/BTC por su tendencia de fondo bajista de fondo, ver diagnostico en
`pendiente_veto_canal_percentil.py`), pero al usarlo SOLO se pierde
proteccion en dias que el criterio absoluto si detectaba bien en BTC. Un
OR conserva ambas fuentes de proteccion en vez de intercambiar una por
otra.

Resultado (17-sept-2026): mejora XRP de verdad sin romper BTC, pero no es
una victoria limpia -- es un trade-off:

  moneda   absoluto(adoptado)   percentil(descartado)   UNION(este fichero)
  BTC      p=0.0150 (mejor)     p=0.2700 (mal)          p=0.0267 (sigue pasando <0.05, pero con menos margen)
  XRP      p=0.3550 (mal)       p=0.1133               p=0.1900 (mejora real, aun no significativo)
  ETH      total=10692.97       total=10775.68          total=10728.39 (sin caida, sano)

Veredicto: alternativa real, no reemplazo automatico de la version
adoptada. Si BTC (la moneda que motivo toda esta investigacion) es la
prioridad, la version absoluta (0.5) sigue siendo mejor. Si se prefiere
dejar de penalizar tanto a XRP a cambio de algo de margen en BTC, esta es
la mejor opcion encontrada hasta ahora -- mejor que la version percentil
pura en las dos monedas simultaneamente. Decision pendiente del usuario:
¿se prioriza a BTC (mantener version actual) o se acepta este trade-off
para mejorar XRP? Ver `registro/intentos.jsonl`.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.pendiente_veto_canal import _en_tendencia_confirmada, simular_cuenta_veto_canal
from laboratorio.patrones.pendiente_veto_canal_percentil import _en_tendencia_confirmada_percentil
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp

MONEDAS = {"ETH": lambda: cargar("ETHUSDT"), "BTC": lambda: cargar("BTCUSDT"), "XRP": cargar_xrp}
UMBRAL_ABS = 0.5
VENTANA_HIST, PERCENTIL = 20, 0.5
SEMILLA = 42
N_PERM = {"ETH": 500, "BTC": 300, "XRP": 300}


def en_tendencia_union(df, direccion):
    en_abs = _en_tendencia_confirmada(df, direccion, umbral_prob_forma=UMBRAL_ABS)
    en_pct = _en_tendencia_confirmada_percentil(df, direccion, PERCENTIL, ventana_historial=VENTANA_HIST)
    return en_abs | en_pct


def _total(df, atr, rt, rs, pend, fechas, en_largo, en_corto, cand_por_año):
    total, por_año = 0.0, {}
    for año in AÑOS:
        cap = simular_cuenta_veto_canal(df, cand_por_año[año], atr, rt, rs, pend, fechas, en_largo, en_corto)
        por_año[año] = round(cap, 2)
        total += cap
    return total, por_año


if __name__ == "__main__":
    for nombre, cargador in MONEDAS.items():
        df, atr, rt, rs, pend, cl, cc = cargador()
        fechas = df["open_time"]
        n = len(df)
        cand_por_año = {año: candidatos_por_año(df, año) for año in AÑOS}

        en_l = en_tendencia_union(df, "largo")
        en_c = en_tendencia_union(df, "corto")
        total, por_año = _total(df, atr, rt, rs, pend, fechas, en_l, en_c, cand_por_año)
        print(f"{nombre}: TOTAL={total:.2f}  por_año={por_año}  dias_largo={int(en_l.sum())}  dias_corto={int(en_c.sum())}")

        rng = np.random.default_rng(SEMILLA)
        idx_validos = np.arange(n)
        n_largo, n_corto = int(en_l.sum()), int(en_c.sum())
        totales_azar = []
        for _ in range(N_PERM[nombre]):
            en_l_azar = np.zeros(n, dtype=bool)
            en_c_azar = np.zeros(n, dtype=bool)
            en_l_azar[rng.choice(idx_validos, size=n_largo, replace=False)] = True
            en_c_azar[rng.choice(idx_validos, size=n_corto, replace=False)] = True
            cap_azar, _ = _total(df, atr, rt, rs, pend, fechas, en_l_azar, en_c_azar, cand_por_año)
            totales_azar.append(cap_azar)
        totales_azar = np.array(totales_azar)
        p_valor = float(np.mean(totales_azar >= total))
        print(f"  Monte Carlo ({N_PERM[nombre]} perms): media_azar={totales_azar.mean():.2f}  p-valor={p_valor:.4f}\n")
