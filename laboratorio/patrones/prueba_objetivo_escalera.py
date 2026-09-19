"""
14-sept-2026: idea del usuario ("¿el take profit se puede ir moviendo en una
subida?") propuesta por mi como diseño concreto: un objetivo EN ESCALERA en
vez de un techo fijo. Motivado por el hallazgo de la sesion: la subida de
ETH de enero-marzo 2024 (+83%) se capturaba en trocitos pequeños porque el
objetivo fijo (o racha rota) cerraba el trade en cuanto se alcanzaba,
dejando la mayor parte de la subida sin coger.

Mecanica: el trade abre con el stop y el objetivo ya elegidos (K=1.2,
R_FIJO=4.0, los mejores encontrados hoy). Si el precio ALCANZA el objetivo
en vez de cerrar la operacion:
  1. se sube el stop hasta el nivel del objetivo alcanzado menos un margen
     de seguridad (RIESGO_BASE_PCT de retroceso, en unidades de riesgo
     inicial) -- para GARANTIZAR que como minimo se conserva esa ganancia.
  2. se extiende el objetivo EXTENSION_R * riesgo mas alla del anterior.
Esto se repite cada vez que el nuevo objetivo se alcanza -- es una
escalera, no un unico salto. El trade solo cierra por: el stop
(ahora en escalera, nunca baja), racha_rota+caida de pendiente, o tiempo
maximo -- ya NO hay un "objetivo" que cierre para siempre.

Barrido de EXTENSION_R (cuanto se extiende cada escalon) y MARGEN_R
(cuanto retroceso se permite antes de saltar el stop en escalera).
Ajuste SOLO en ETH 2024, confirmacion sin tocar nada en BTC 2024,
multi-anio despues.
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
from laboratorio.patrones.prueba_racha_filtrada_por_pendiente import _pendiente_atr
from motores.volatilidad import atr_absoluto
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, N_LEN, M_DIAS, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

UMBRAL_SWITCH = 0.0
UMBRAL_CAIDA_FILTRO = 0.3
K_ATR_STOP = 1.2
R_FIJO = 4.0
EXTENSION_R_GRID = [999, 4.0, 3.0, 2.0, 1.5, 1.0, 0.5]
# 999 = sin escalera (objetivo fijo de siempre, el sistema recien elegido)
MARGEN_R_GRID = [0.3, 0.5, 0.8]


def _simular_trade_manual(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                           senal_externa, pendiente, umbral_caida_filtro, extension_r, margen_r):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    riesgo_precio = abs(precio_entrada - niveles.stop)
    stop_actual = niveles.stop
    objetivo_actual = niveles.objetivo
    escalera_activa = extension_r < 999
    pendiente_extremo = 0.0
    for i in range(idx_entrada + 1, fin + 1):
        if direccion == "largo":
            toca_stop = low[i] <= stop_actual
        else:
            toca_stop = high[i] >= stop_actual
        if toca_stop:
            return i, stop_actual, "stop"

        if direccion == "largo":
            toca_objetivo = high[i] >= objetivo_actual
        else:
            toca_objetivo = low[i] <= objetivo_actual
        if toca_objetivo:
            if not escalera_activa:
                return i, objetivo_actual, "objetivo"
            # escalera: sube el stop hasta (objetivo actual - margen) y extiende el objetivo
            if direccion == "largo":
                stop_actual = max(stop_actual, objetivo_actual - margen_r * riesgo_precio)
                objetivo_actual = objetivo_actual + extension_r * riesgo_precio
            else:
                stop_actual = min(stop_actual, objetivo_actual + margen_r * riesgo_precio)
                objetivo_actual = objetivo_actual - extension_r * riesgo_precio

        if senal_externa is not None and senal_externa[i]:
            p = pendiente[i]
            if not np.isnan(p):
                if direccion == "largo":
                    pendiente_extremo = max(pendiente_extremo, p)
                    listón = pendiente_extremo * (1 - umbral_caida_filtro)
                    honra_corte = pendiente_extremo <= 0 or p <= listón
                else:
                    pendiente_extremo = min(pendiente_extremo, p)
                    listón = pendiente_extremo * (1 - umbral_caida_filtro)
                    honra_corte = pendiente_extremo >= 0 or p >= listón
                if honra_corte:
                    return i, close[i], "senal_externa"
            else:
                return i, close[i], "senal_externa"
        else:
            p = pendiente[i]
            if not np.isnan(p):
                if direccion == "largo":
                    pendiente_extremo = max(pendiente_extremo, p)
                else:
                    pendiente_extremo = min(pendiente_extremo, p)
    return fin, close[fin], "tiempo_maximo"


def _simular(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente, umbral_switch, umbral_caida, extension_r, margen_r):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = _simular_trade_manual(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal, pendiente,
                                   umbral_caida, extension_r, margen_r)
        if r is None:
            return None
        idx_salida, precio_salida, motivo = r
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        return {"idx_entrada": idx, "direccion": direccion, "probabilidad": prob,
                "idx_salida": idx_salida, "precio_entrada": close[idx], "precio_salida": precio_salida,
                "unidades": pos.unidades}

    def _cerrar(pos, idx_cierre, precio_cierre):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl = pos["unidades"] * (precio_cierre - pos["precio_entrada"]) * signo
        capital += pnl
        curva.append((fechas.iloc[idx_cierre], capital))
        trades.append({"pnl_eur": pnl})

    for idx, direccion, prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        if abierta is not None and idx > abierta["idx_salida"]:
            _cerrar(abierta, abierta["idx_salida"], abierta["precio_salida"])
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
        _cerrar(abierta, abierta["idx_salida"], abierta["precio_salida"])

    valores = np.array([c for _, c in curva])
    pico = np.maximum.accumulate(valores)
    drawdown_max_pct = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)
    return capital, len(trades), ganadoras, drawdown_max_pct


def _cargar(moneda):
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_objetivo_escalera")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    pendiente = _pendiente_atr(df, atr)
    return df, atr, racha_rota_techo, racha_rota_suelo, pendiente


def ajuste_eth_2024():
    print("=== Ajuste objetivo en escalera (EXTENSION_R x MARGEN_R) -- SOLO ETH 2024 ===")
    df, atr, rt, rs, pendiente = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    cap_base, n_b, gan_b, dd_b = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 999, 0.5)
    print(f"  baseline (K=1.2,R=4.0, objetivo fijo): {cap_base:.2f}€ -- {n_b} trades, {gan_b} ganadoras, dd {dd_b:.2f}%")
    mejor = None
    for ext in EXTENSION_R_GRID:
        if ext >= 999:
            continue
        for margen in MARGEN_R_GRID:
            cap, n, gan, dd = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, ext, margen)
            print(f"  EXTENSION_R={ext}, MARGEN_R={margen}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
                  f"{n} trades, {gan} ganadoras ({gan/n*100:.0f}%), dd {dd:.2f}%")
            if mejor is None or cap > mejor[2]:
                mejor = (ext, margen, cap)
    print(f"  -> mejor: EXTENSION_R={mejor[0]}, MARGEN_R={mejor[1]} ({mejor[2]:.2f}€) vs baseline {cap_base:.2f}€")
    return mejor[0], mejor[1]


def confirmar_y_multi_anio(ext_elegido, margen_elegido):
    print(f"\n=== Confirmacion BTC 2024 y multi-anio con EXTENSION_R={ext_elegido}, MARGEN_R={margen_elegido} (congelado) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pendiente = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 999, 0.5)
            cap_nuevo, n_n, gan_n, dd_n = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, ext_elegido, margen_elegido)
            gana = cap_nuevo > cap_actual
            print(f"  {año}: fijo {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"escalera {cap_nuevo:.2f}€ ({n_n}/{gan_n}, dd {dd_n:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append(gana)
    print(f"\nResultado: gana en {sum(resultados)} de {len(resultados)} combinaciones")


if __name__ == "__main__":
    ext, margen = ajuste_eth_2024()
    confirmar_y_multi_anio(ext, margen)
