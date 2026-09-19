"""
15-sept-2026: el usuario senalo un patron real en el rally de ETH de
enero-marzo 2024 -- tres operaciones (largo 25-ene +12.77e, corto 20-feb
+7.18e, largo 23-feb +5.49e) se cortan por racha rota mientras la
tendencia de fondo sigue intacta y mucho mas grande (~+80% en el mismo
tramo). Pregunta del usuario: "?como distinguimos una racha rota que es
ruido dentro de una subida fuerte, de una racha rota que es un cambio de
tendencia de verdad?" -- propone usar la BRUSQUEDAD/velocidad de la
subida como filtro.

Idea a probar: la racha rota solo se respeta como salida si el impulso
reciente (pendiente del precio en el mismo M_DIAS que ya usa la racha,
normalizada por ATR para que sea comparable entre monedas/epocas) se ha
enfriado de verdad -- si la tendencia sigue siendo fuerte en la MISMA
direccion de la posicion, se ignora la senal de racha rota y se deja
correr la operacion (el stop/objetivo/dias_maximo de siempre siguen
activos por debajo, esto NO desactiva la proteccion de perdidas, solo
evita cortar ganancias por ruido en medio de una tendencia fuerte).

Barrido del umbral de pendiente (en unidades de ATR sobre M_DIAS), no un
numero fijo a ojo -- 999 = filtro desactivado (comportamiento actual).
Ajuste SOLO en ETH 2024, confirmacion sin tocar nada en BTC 2024, y
despues multi-anio si supera la confirmacion.
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
from motores.volatilidad import atr_absoluto
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, N_LEN, M_DIAS, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade
from tamano.tamano import calcular_tamano

UMBRAL_SWITCH = 0.0
UMBRAL_PENDIENTE_GRID = [999, 3.0, 2.0, 1.5, 1.0, 0.5, 0.0, -0.5, -1.0]  # unidades de ATR sobre M_DIAS; 999 = desactivado


def _pendiente_atr(df, atr):
    close = df["close"].to_numpy()
    n = len(close)
    pendiente = np.full(n, np.nan)
    for i in range(M_DIAS, n):
        if atr[i] > 0 and not np.isnan(atr[i]):
            pendiente[i] = (close[i] - close[i - M_DIAS]) / atr[i]
    return pendiente


def _filtrar_por_pendiente(racha_rota, pendiente, direccion, umbral):
    """direccion='largo': ignora la senal de racha_rota_techo si la pendiente
    reciente SIGUE siendo fuertemente alcista (> umbral) -- solo se respeta
    si el impulso ya se enfrio. direccion='corto': espejo, pendiente < -umbral."""
    if umbral >= 999:
        return racha_rota
    filtrada = racha_rota.copy()
    for i in range(len(racha_rota)):
        if not filtrada[i]:
            continue
        if np.isnan(pendiente[i]):
            continue
        if direccion == "largo" and pendiente[i] > umbral:
            filtrada[i] = False
        if direccion == "corto" and pendiente[i] < -umbral:
            filtrada[i] = False
    return filtrada


def _simular(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, umbral_switch):
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


def _cargar(moneda):
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_racha_filtrada_por_pendiente")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    pendiente = _pendiente_atr(df, atr)
    return df, atr, racha_rota_techo, racha_rota_suelo, pendiente


def ajuste_eth_2024():
    print("=== Ajuste del umbral de pendiente (ATR sobre M_DIAS) -- SOLO ETH 2024 ===")
    df, atr, rt, rs, pendiente = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    mejor = None
    for umbral in UMBRAL_PENDIENTE_GRID:
        rt_f = _filtrar_por_pendiente(rt, pendiente, "largo", umbral)
        rs_f = _filtrar_por_pendiente(rs, pendiente, "corto", umbral)
        cap, n, gan, dd = _simular(df, cand, atr, rt_f, rs_f, UMBRAL_SWITCH)
        etiqueta = "desactivado (baseline)" if umbral >= 999 else f"{umbral:+.1f} ATR"
        print(f"  umbral_pendiente={etiqueta}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
              f"{n} trades, {gan} ganadoras, dd {dd:.2f}%")
        if mejor is None or cap > mejor[1]:
            mejor = (umbral, cap)
    print(f"  -> mejor umbral en ETH 2024: {mejor[0]} ({mejor[1]:.2f}€)")
    return mejor[0]


def confirmar_y_multi_anio(umbral_elegido):
    print(f"\n=== Confirmacion BTC 2024 y multi-anio con umbral={umbral_elegido} (congelado) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pendiente = _cargar(moneda)
        rt_f = _filtrar_por_pendiente(rt, pendiente, "largo", umbral_elegido)
        rs_f = _filtrar_por_pendiente(rs, pendiente, "corto", umbral_elegido)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a = _simular(df, cand, atr, rt, rs, UMBRAL_SWITCH)
            cap_nuevo, n_n, gan_n, dd_n = _simular(df, cand, atr, rt_f, rs_f, UMBRAL_SWITCH)
            gana = cap_nuevo > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"con filtro pendiente {cap_nuevo:.2f}€ ({n_n}/{gan_n}, dd {dd_n:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append(gana)
    print(f"\nResultado: gana en {sum(resultados)} de {len(resultados)} combinaciones")


if __name__ == "__main__":
    umbral = ajuste_eth_2024()
    if umbral < 999:
        confirmar_y_multi_anio(umbral)
    else:
        print("\nEl mejor umbral encontrado es 'desactivado' -- el filtro no aporta en ETH 2024.")
