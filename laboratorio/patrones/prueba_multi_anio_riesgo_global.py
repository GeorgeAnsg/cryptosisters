"""
18-sept-2026: repetir la tabla multi-año de `prueba_multi_anio.py` (ya
validada: cambio de candidato gana en las 8 combinaciones 2021-2024,
ETH/BTC) pero con el multiplicador de riesgo global (`cartera/riesgo_global.py`)
puesto de verdad, en vez de dimensionar cada posición de forma aislada.

Por qué hacía falta: `cartera/README.md` avisaba explícitamente de que los
resultados de multi-posición/switch estaban sobreestimados sin ningún tope
al riesgo conjunto -- con solo 1 hueco por activo (nunca 2 posiciones a la
vez en la misma moneda) el riesgo nunca se ACUMULA entre posiciones, pero
sí puede estar ENTRANDO a tamaño completo justo en el peor momento (una
sacudida de volatilidad, el mismo escenario que motivó crear
`riesgo_global.py`). Aplicar el multiplicador al ABRIR cada posición
(reduce las unidades compradas, nunca bloquea la entrada) es la forma
correcta de probarlo con 1 solo hueco -- el otro componente de
riesgo_global (correlación entre posiciones simultáneas) no aplica aquí
por construcción, ya está documentado como pendiente para cuando haya más
solape real entre motores.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from cartera.riesgo_global import multiplicador_por_volatilidad
from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.barrido_racha_tendencia import _puntos_confirmados, _racha_rota
from laboratorio.patrones.prueba_multi_anio import AÑOS, UMBRAL_SWITCH, candidatos_por_año
from motores import doble_suelo as suelo_motor
from motores import doble_techo as techo_motor
from motores.volatilidad import atr_absoluto
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, N_LEN, M_DIAS, R_FIJO, RIESGO_BASE_PCT,
)
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade
from tamano.tamano import calcular_tamano


def _simular_con_switch_y_riesgo_global(df, candidatos, atr, mult_riesgo, racha_rota_techo, racha_rota_suelo, umbral_switch):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal_externa=senal)
        if t is None:
            return None
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        m = mult_riesgo[idx]
        m = 1.0 if np.isnan(m) else m
        return {"idx_entrada": idx, "direccion": direccion, "probabilidad": prob, "t": t,
                "unidades": pos.unidades * m, "mult_riesgo": m}

    def _cerrar(pos, idx_cierre, precio_cierre):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl = pos["unidades"] * (precio_cierre - pos["t"].precio_entrada) * signo
        capital += pnl
        curva.append((fechas.iloc[idx_cierre], capital))
        trades.append({"pnl_eur": pnl, "mult_riesgo": pos["mult_riesgo"]})

    for idx, direccion, prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        if abierta is not None and idx > abierta["t"].idx_salida:
            _cerrar(abierta, abierta["t"].idx_salida, abierta["t"].precio_salida)
            abierta = None
        if abierta is None:
            nueva = _abrir(idx, direccion, prob)
            if nueva is not None:
                abierta = nueva
            continue
        if direccion != abierta["direccion"] and prob - abierta["probabilidad"] >= umbral_switch:
            _cerrar(abierta, idx, close[idx])
            nueva = _abrir(idx, direccion, prob)
            abierta = nueva

    if abierta is not None:
        _cerrar(abierta, abierta["t"].idx_salida, abierta["t"].precio_salida)

    valores = np.array([c for _, c in curva])
    pico = np.maximum.accumulate(valores)
    drawdown_max_pct = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)
    mult_medio = np.mean([t["mult_riesgo"] for t in trades]) if trades else 1.0
    return capital, len(trades), ganadoras, drawdown_max_pct, mult_medio


def main():
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_multi_anio_riesgo_global")
        atr = atr_absoluto(df)
        mult_riesgo = multiplicador_por_volatilidad(df).to_numpy()
        n = len(df)
        puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
        puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
        racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
        racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")

        print(f"\n=== {moneda} ===")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_sw, n_sw, gan_sw, dd_sw, _ = _simular_con_switch_y_riesgo_global(
                df, cand, atr, mult_riesgo, racha_rota_techo, racha_rota_suelo, umbral_switch=999)
            cap_rg, n_rg, gan_rg, dd_rg, mult_medio = _simular_con_switch_y_riesgo_global(
                df, cand, atr, mult_riesgo, racha_rota_techo, racha_rota_suelo, umbral_switch=UMBRAL_SWITCH)
            idxs = [i for i, f in enumerate(df["open_time"]) if f.year == año]
            precio_ini, precio_fin = df["close"].iloc[idxs[0]], df["close"].iloc[idxs[-1]]
            retorno_hold = (precio_fin / precio_ini - 1) * 100
            print(f"  {año} (buy&hold {retorno_hold:+.1f}%, {len(cand)} candidatos):")
            print(f"    sin cambio: {cap_sw:.2f}€ ({(cap_sw/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
                  f"{n_sw} trades, {gan_sw} ganadoras, dd {dd_sw:.2f}%")
            print(f"    con cambio + riesgo global: {cap_rg:.2f}€ ({(cap_rg/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
                  f"{n_rg} trades, {gan_rg} ganadoras, dd {dd_rg:.2f}%, mult.riesgo medio={mult_medio:.2f}")


if __name__ == "__main__":
    main()
