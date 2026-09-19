"""
14-sept-2026: el usuario señalo que el stop-loss parece "super permisivo".
Comprobado con datos: K_ATR_STOP=2.5 (el valor actual, fijado hace tiempo
sin barrer en el escenario switch) produce stops de 8.8%-21.4% en los
propios trades perdedores analizados, con una MEDIA de 12.56% y un MAXIMO
de 22% en todo ETH 2024 -- efectivamente enorme para un mecanismo pensado
para "cortar rapido lo que va mal". El objetivo (R_FIJO=3.0) es aun mas
lejano (3x el stop): 26%-64% en esos mismos trades, lo que explica por que
tan pocos trades cierran por "objetivo".

Esta prueba barre K_ATR_STOP manteniendo R_FIJO=3.0 fijo (el objetivo
sigue siendo 3R, solo cambia lo ancho que es cada R), sobre el sistema
real (racha_rota + caida relativa de pendiente, umbral 30%, ya congelado).
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
    MULTIPLICADOR_MIN, N_LEN, M_DIAS, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

UMBRAL_SWITCH = 0.0
UMBRAL_CAIDA_FILTRO = 0.3
K_ATR_STOP_GRID = [2.5, 2.0, 1.75, 1.5, 1.25, 1.0, 0.75]


def _simular_trade_manual(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                           senal_externa, pendiente, umbral_caida_filtro):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    pendiente_extremo = 0.0
    for i in range(idx_entrada + 1, fin + 1):
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


def _simular(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente, umbral_switch, umbral_caida, k_atr_stop):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, k_atr_stop, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = _simular_trade_manual(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal, pendiente, umbral_caida)
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
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_stop_mas_ceñido")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    pendiente = _pendiente_atr(df, atr)
    return df, atr, racha_rota_techo, racha_rota_suelo, pendiente


def ajuste_eth_2024():
    print("=== Ajuste: K_ATR_STOP (ancho del stop) sobre el sistema real -- SOLO ETH 2024 ===")
    df, atr, rt, rs, pendiente = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    mejor = None
    for k in K_ATR_STOP_GRID:
        cap, n, gan, dd = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, k)
        etiqueta = "actual" if k == 2.5 else ""
        print(f"  K_ATR_STOP={k}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
              f"{n} trades, {gan} ganadoras, dd {dd:.2f}% {etiqueta}")
        if mejor is None or cap > mejor[1]:
            mejor = (k, cap)
    print(f"  -> mejor: K_ATR_STOP={mejor[0]} ({mejor[1]:.2f}€)")
    return mejor[0]


def confirmar_y_multi_anio(k_elegido):
    print(f"\n=== Confirmacion BTC 2024 y multi-anio con K_ATR_STOP={k_elegido} (congelado) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pendiente = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 2.5)
            cap_nuevo, n_n, gan_n, dd_n = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, k_elegido)
            gana = cap_nuevo > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"stop mas ceñido {cap_nuevo:.2f}€ ({n_n}/{gan_n}, dd {dd_n:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append(gana)
    print(f"\nResultado: gana en {sum(resultados)} de {len(resultados)} combinaciones")


if __name__ == "__main__":
    k = ajuste_eth_2024()
    confirmar_y_multi_anio(k)
