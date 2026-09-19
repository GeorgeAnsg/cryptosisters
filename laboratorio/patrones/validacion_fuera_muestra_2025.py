"""Prueba fuera de muestra real: sistema congelado (sistema_confirmado_switch_14sept2026.py)
corrido sobre 2025, un tramo que NUNCA se ha usado para ajustar nada en este proyecto
(bloqueado por defecto detras de acceso_validacion=True en cargar_ohlcv_lab).

No se toca ni un parametro. Objetivo: comprobar si el resultado se sostiene fuera del
periodo (2021-2024) usado en todas las sesiones de ajuste, o si se derrumba (senal de
sobreajuste acumulado).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.barrido_racha_tendencia import _puntos_confirmados, _racha_rota
from laboratorio.patrones.prueba_racha_filtrada_por_pendiente import _pendiente_atr
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año
from laboratorio.patrones.sistema_confirmado_switch_14sept2026 import (
    N_LEN, M_DIAS, simular_cuenta, CAPITAL_INICIAL,
)
from motores.volatilidad import atr_absoluto

MOTIVO = "Prueba fuera de muestra tras cierre de ajuste del escenario switch (14-sept-2026): comprobar si el sistema congelado se sostiene en 2025, tramo nunca usado para tunear."


def cargar_2025(moneda):
    df = cargar_ohlcv_lab(
        moneda, "1d",
        estrategia="validacion_fuera_muestra_2025",
        acceso_validacion=True,
        motivo=MOTIVO,
    )
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    pendiente = _pendiente_atr(df, atr)
    return df, atr, racha_rota_techo, racha_rota_suelo, pendiente


if __name__ == "__main__":
    print("=== Fuera de muestra 2025 -- sistema CONGELADO, cero parametros tocados ===\n")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pendiente = cargar_2025(moneda)
        cand = candidatos_por_año(df, 2025)
        cap, trades, gan, dd = simular_cuenta(df, cand, atr, rt, rs, pendiente, df["open_time"])
        pct = (cap / CAPITAL_INICIAL - 1) * 100
        wr = gan / len(trades) * 100 if trades else 0
        print(f"{moneda} 2025: {cap:.2f}€ ({pct:+.1f}%) -- {len(trades)} trades, {gan} ganadoras ({wr:.0f}%), drawdown {dd:.2f}%")
        resultados.append({"moneda": moneda, "año": 2025, "capital": cap, "pct": pct,
                            "n_trades": len(trades), "ganadoras": gan, "dd": dd})

    import json
    with open("/tmp/validacion_fuera_muestra_2025.json", "w") as f:
        json.dump(resultados, f, indent=2)
