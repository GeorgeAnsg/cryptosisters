"""
Monte Carlo por permutacion (16-sept-2026) sobre la version final de
`pendiente_veto_canal_percentil.py`: ventana_historial=20, percentil_umbral=0.5.

Ajuste en ETH (ver `pendiente_veto_canal_percentil.py` __main__): el grid
2D ventana x percentil tenia un pico aislado en (ventana=12, percentil=0.7,
total=10777.45) que al confirmar en BTC resultaba en CERO mejora en 2023
(identico a sin_filtro, 1612.98) -- exactamente el patron de "pico de borde
no confiable" (ver leccion 0008 del log de observaciones, aplicada aqui a
un grid 2D). Los vecinos inmediatos (ventana=15 y ventana=20 con
percentil=0.5-0.6) dan un total en ETH practicamente identico (10775.68,
apenas 1.77 menos) formando una meseta estable en varias celdas del grid,
y SI mejoran BTC 2023 (1725.78, igual que la version de umbral absoluto) y
dan a XRP su mejor resultado de toda la investigacion. Se congela
ventana_historial=20, percentil_umbral=0.5 por ser el centro de esa meseta
estable, no el pico aislado.

Metodologia identica a `validacion_puertas_regimen_neutro.py` (seccion 2):
barajar que dias quedan marcados "en tendencia confirmada" (mismo recuento
que el real) y comparar el total real contra la distribucion de colocar esa
misma cantidad de dias al azar. Se hace por separado para largo y corto
(cada uno con su propio recuento real de dias activos), porque son masks
independientes que protegen operaciones en direcciones distintas.
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np

from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
from laboratorio.patrones.pendiente_veto_canal import simular_cuenta_veto_canal
from laboratorio.patrones.pendiente_veto_canal_percentil import (
    _confirmados_ordenados, _activo_desde_confirmados,
)

MONEDAS = {"ETH": lambda: cargar("ETHUSDT"), "BTC": lambda: cargar("BTCUSDT"), "XRP": cargar_xrp}

VENTANA_HISTORIAL_FINAL = 20
PERCENTIL_UMBRAL_FINAL = 0.5
SEMILLA = 42
N_PERM = {"ETH": 500, "BTC": 300, "XRP": 300}


def _total(df, atr, rt, rs, pend, fechas, en_largo, en_corto, cand_por_año):
    total = 0.0
    for año in AÑOS:
        total += simular_cuenta_veto_canal(df, cand_por_año[año], atr, rt, rs, pend, fechas, en_largo, en_corto)
    return total


if __name__ == "__main__":
    resultados = {}
    for nombre, cargador in MONEDAS.items():
        df, atr, rt, rs, pend, cl, cc = cargador()
        fechas = df["open_time"]
        n = len(df)
        cand_por_año = {año: candidatos_por_año(df, año) for año in AÑOS}

        conf_l = _confirmados_ordenados(df, "largo")
        conf_c = _confirmados_ordenados(df, "corto")
        en_l_real = _activo_desde_confirmados(conf_l, n, PERCENTIL_UMBRAL_FINAL, VENTANA_HISTORIAL_FINAL)
        en_c_real = _activo_desde_confirmados(conf_c, n, PERCENTIL_UMBRAL_FINAL, VENTANA_HISTORIAL_FINAL)
        n_largo, n_corto = int(en_l_real.sum()), int(en_c_real.sum())
        total_real = _total(df, atr, rt, rs, pend, fechas, en_l_real, en_c_real, cand_por_año)

        rng = np.random.default_rng(SEMILLA)
        idx_validos = np.arange(n)
        totales_azar = []
        for _ in range(N_PERM[nombre]):
            en_l_azar = np.zeros(n, dtype=bool)
            en_c_azar = np.zeros(n, dtype=bool)
            en_l_azar[rng.choice(idx_validos, size=n_largo, replace=False)] = True
            en_c_azar[rng.choice(idx_validos, size=n_corto, replace=False)] = True
            totales_azar.append(_total(df, atr, rt, rs, pend, fechas, en_l_azar, en_c_azar, cand_por_año))
        totales_azar = np.array(totales_azar)
        p_valor = float(np.mean(totales_azar >= total_real))
        resultados[nombre] = dict(total_real=total_real, media_azar=float(totales_azar.mean()), p_valor=p_valor,
                                   n_largo=n_largo, n_corto=n_corto)
        print(f"{nombre}: real={total_real:.2f}  media_azar={totales_azar.mean():.2f}  p-valor={p_valor:.4f}  "
              f"(dias_largo={n_largo}, dias_corto={n_corto}, {N_PERM[nombre]} permutaciones)")
