"""
14-sept-2026: el usuario señalo la causa raiz directamente -- "no hay
proteccion de ganancia". Revisando las pruebas anteriores (retroceso desde
el pico, caida relativa de pendiente, velocidad de subida) se confirma que
NINGUNA de ellas era realmente un mecanismo independiente: todas estaban
condicionadas a que racha_rota se disparase primero (o, en las versiones
"independientes" mal comparadas, sin racha_rota en absoluto -- ver
observacion 0018). Nunca se ha probado un trailing-stop de verdad: activado
solo por la propia ganancia de LA OPERACION (en R, multiplos del riesgo
inicial), sin depender de ningun patron ni de racha_rota.

Mecanica: una vez el trade alcanza un nivel de ganancia >= UMBRAL_R * riesgo
inicial, se activa un trailing-stop que sigue al maximo (largo) o minimo
(corto) favorable alcanzado desde la entrada, a una distancia de
MULT_ATR_TRAIL * atr del dia de la entrada. Mientras no se alcance ese
nivel de ganancia, el trailing no esta activo y el trade sigue protegido
solo por el stop/objetivo/racha_rota+caida de siempre -- este mecanismo es
ADICIONAL, no sustituye nada.

Barrido de UMBRAL_R (a partir de cuantas R empieza a proteger) x
MULT_ATR_TRAIL (que tan ceñido es el trailing). Ajuste SOLO en ETH 2024,
confirmacion sin tocar nada en BTC 2024, multi-anio despues.
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
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, N_LEN, M_DIAS, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

UMBRAL_SWITCH = 0.0
UMBRAL_CAIDA_FILTRO = 0.3
UMBRAL_R_GRID = [999, 3.0, 2.5, 2.0, 1.5, 1.0, 0.75, 0.5]
MULT_ATR_TRAIL_GRID = [1.0, 1.5, 2.0, 2.5]


def _simular_trade_manual(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo, atr_entrada,
                           senal_externa, pendiente, umbral_caida_filtro, umbral_r, mult_atr_trail):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    riesgo_precio = abs(precio_entrada - niveles.stop)
    pendiente_extremo = 0.0
    trailing_activo = False
    extremo_favorable = precio_entrada
    for i in range(idx_entrada + 1, fin + 1):
        if direccion == "largo":
            extremo_favorable = max(extremo_favorable, high[i])
            ganancia_r = (extremo_favorable - precio_entrada) / riesgo_precio
        else:
            extremo_favorable = min(extremo_favorable, low[i])
            ganancia_r = (precio_entrada - extremo_favorable) / riesgo_precio

        if umbral_r < 999 and not trailing_activo and ganancia_r >= umbral_r:
            trailing_activo = True

        if trailing_activo:
            distancia = mult_atr_trail * atr_entrada
            if direccion == "largo":
                stop_trailing = extremo_favorable - distancia
                toca_trailing = low[i] <= stop_trailing
            else:
                stop_trailing = extremo_favorable + distancia
                toca_trailing = high[i] >= stop_trailing
            if toca_trailing:
                return i, stop_trailing, "trailing_ganancia"

        if direccion == "largo":
            toca_stop = low[i] <= niveles.stop
            toca_objetivo = high[i] >= niveles.objetivo
        else:
            toca_stop = high[i] >= niveles.stop
            toca_objetivo = low[i] <= niveles.objetivo
        if toca_stop:
            return i, niveles.stop, "stop"
        if toca_objetivo:
            return i, niveles.objetivo, "objetivo"

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


def _simular(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente,
             umbral_switch, umbral_caida_filtro, umbral_r, mult_atr_trail):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = _simular_trade_manual(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, atr[idx], senal, pendiente,
                                   umbral_caida_filtro, umbral_r, mult_atr_trail)
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
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_trailing_stop_independiente")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    pendiente = _pendiente_atr(df, atr)
    return df, atr, racha_rota_techo, racha_rota_suelo, pendiente


def ajuste_eth_2024():
    print("=== Ajuste: trailing-stop por ganancia (UMBRAL_R x MULT_ATR) sobre el sistema real -- SOLO ETH 2024 ===")
    df, atr, rt, rs, pendiente = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    cap_base, n_b, gan_b, dd_b = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 999, 1.5)
    print(f"  baseline real (racha_rota+caida, sin trailing): {cap_base:.2f}€ ({(cap_base/CAPITAL_INICIAL-1)*100:+.1f}%) -- {n_b} trades, {gan_b} ganadoras, dd {dd_b:.2f}%")
    mejor = None
    for umbral_r in UMBRAL_R_GRID:
        if umbral_r >= 999:
            continue
        for mult in MULT_ATR_TRAIL_GRID:
            cap, n, gan, dd = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, umbral_r, mult)
            print(f"  umbral_r={umbral_r}R, mult_atr={mult}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
                  f"{n} trades, {gan} ganadoras, dd {dd:.2f}%")
            if mejor is None or cap > mejor[2]:
                mejor = (umbral_r, mult, cap)
    print(f"  -> mejor: umbral_r={mejor[0]}R, mult_atr={mejor[1]} ({mejor[2]:.2f}€) vs baseline {cap_base:.2f}€")
    return mejor[0], mejor[1]


def confirmar_y_multi_anio(umbral_r_elegido, mult_elegido):
    print(f"\n=== Confirmacion BTC 2024 y multi-anio con umbral_r={umbral_r_elegido}R, mult_atr={mult_elegido} (congelado) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pendiente = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 999, mult_elegido)
            cap_nuevo, n_n, gan_n, dd_n = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, umbral_r_elegido, mult_elegido)
            gana = cap_nuevo > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"con trailing {cap_nuevo:.2f}€ ({n_n}/{gan_n}, dd {dd_n:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append(gana)
    print(f"\nResultado: gana en {sum(resultados)} de {len(resultados)} combinaciones")


if __name__ == "__main__":
    umbral_r, mult = ajuste_eth_2024()
    confirmar_y_multi_anio(umbral_r, mult)
