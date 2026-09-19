"""
Corrección a la validación (15-sept-2026): todas las pruebas de cambio de
candidato fuerte y racha rota se habían ajustado y confirmado SOLO en 2024
-- ETH para ajustar, BTC para confirmar, pero el mismo año en las dos
monedas. Si 2024 tiene algo peculiar (fue un año muy alcista en ambas),
media validación cruzada real puede estar oculta: el usuario señaló
correctamente el riesgo de estar "sobreajustando a un solo gráfico"
(15-sept-2026).

El proyecto tiene datos 2017-2024 (`laboratorio/datos_lab.py`). Aquí se
corre la MISMA cuenta de 1000e (mismo motor, misma señal, mismo cambio de
candidato ya validado con umbral_switch=0.0) en varios años sueltos --
2021 (alcista fuerte), 2022 (bajista fuerte), 2023 (lateral/recuperación)
y 2024 (alcista, ya conocido) -- cada año como cuenta independiente desde
1000e, sin retocar NINGUN parametro entre años. Si el cambio de candidato
solo funciona en mercados alcistas como 2024, tiene que verse aqui.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.barrido_racha_tendencia import _puntos_confirmados, _racha_rota
from motores import doble_suelo as suelo_motor
from motores import doble_techo as techo_motor
from motores.volatilidad import atr_absoluto
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, N_LEN, M_DIAS, R_FIJO, RIESGO_BASE_PCT,
)
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade
from tamano.tamano import calcular_tamano

AÑOS = [2021, 2022, 2023, 2024]
UMBRAL_SWITCH = 0.0  # ganador ya validado en 2024, sin retocar aqui


def candidatos_por_año(df, año):
    fechas = df["open_time"]
    out = []
    for c in techo_motor.detectar(df):
        if fechas.iloc[c.idx_techo2].year != año:
            continue
        r = en_vivo_techo(df, c.idx_techo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_techo2, "corto", r.probabilidad_total_si_confirma))
    for c in suelo_motor.detectar(df):
        if fechas.iloc[c.idx_fondo2].year != año:
            continue
        r = en_vivo_suelo(df, c.idx_fondo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_fondo2, "largo", r.probabilidad_total_si_confirma))
    return sorted(out, key=lambda c: c[0])


def _simular_con_switch(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, umbral_switch):
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
        return {"idx_entrada": idx, "direccion": direccion, "probabilidad": prob, "t": t, "unidades": pos.unidades}

    def _cerrar(pos, idx_cierre, precio_cierre):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl = pos["unidades"] * (precio_cierre - pos["t"].precio_entrada) * signo
        capital += pnl
        curva.append((fechas.iloc[idx_cierre], capital))
        trades.append({"pnl_eur": pnl})

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
    return capital, len(trades), ganadoras, drawdown_max_pct


def main():
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_multi_anio")
        atr = atr_absoluto(df)
        n = len(df)
        puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
        puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
        racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
        racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")

        print(f"\n=== {moneda} ===")
        precio_inicio_año = {}
        for año in AÑOS:
            idxs = [i for i, f in enumerate(df["open_time"]) if f.year == año]
            precio_inicio_año[año] = df["close"].iloc[idxs[0]]
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_base, n_base, gan_base, dd_base = _simular_con_switch(
                df, cand, atr, racha_rota_techo, racha_rota_suelo, umbral_switch=999)
            cap_sw, n_sw, gan_sw, dd_sw = _simular_con_switch(
                df, cand, atr, racha_rota_techo, racha_rota_suelo, umbral_switch=UMBRAL_SWITCH)
            idxs = [i for i, f in enumerate(df["open_time"]) if f.year == año]
            precio_ini, precio_fin = df["close"].iloc[idxs[0]], df["close"].iloc[idxs[-1]]
            retorno_hold = (precio_fin / precio_ini - 1) * 100
            print(f"  {año} (buy&hold {retorno_hold:+.1f}%, {len(cand)} candidatos):")
            print(f"    sin cambio: {cap_base:.2f}€ ({(cap_base/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
                  f"{n_base} trades, {gan_base} ganadoras, dd {dd_base:.2f}%")
            print(f"    con cambio: {cap_sw:.2f}€ ({(cap_sw/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
                  f"{n_sw} trades, {gan_sw} ganadoras, dd {dd_sw:.2f}%")


if __name__ == "__main__":
    main()
